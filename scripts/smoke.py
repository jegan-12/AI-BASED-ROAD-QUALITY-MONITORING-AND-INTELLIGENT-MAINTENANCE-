"""Real HTTP integration smoke test against an isolated temporary SQLite database.

Starts API, inference and worker subprocesses, uploads image/video, checks review/export,
then terminates only those owned processes. Synthetic fixtures never imply model accuracy.
"""
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def main():
    api_port,inference_port=free_port(),free_port()
    with tempfile.TemporaryDirectory(prefix='roadscope-smoke-') as temp:
        root=Path(temp)
        env={**os.environ,'DATABASE_URL':'sqlite:///'+str(root/'test.db'),'MEDIA_DIR':str(root/'media'),
             'JWT_SECRET':secrets.token_hex(32),'INTERNAL_API_KEY':secrets.token_hex(32),
             'DEMO_MODE':'true','INFERENCE_MODE':'demo','INFERENCE_URL':f'http://127.0.0.1:{inference_port}'}
        password=secrets.token_urlsafe(24)
        env['SMOKE_PASSWORD']=password
        setup="""
import os
from backend.app.db import Base,engine,SessionLocal
from backend.app.models import User
from backend.app.security import password_hash
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(User(username='smoke-inspector',role='inspector',password_hash=password_hash.hash(os.environ['SMOKE_PASSWORD'])))
    db.commit()
"""
        subprocess.run([sys.executable,'-c',setup],env=env,check=True)
        env.pop('SMOKE_PASSWORD')
        processes=[]
        logs=[]
        try:
            commands=[['-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(api_port)],
                      ['-m','uvicorn','inference.service:app','--host','127.0.0.1','--port',str(inference_port)],
                      ['-m','backend.app.worker']]
            for index,command in enumerate(commands):
                stream=(root/f'service-{index}.log').open('w')
                logs.append(stream)
                processes.append(subprocess.Popen([sys.executable,*command],env=env,stdout=stream,stderr=stream))
            with httpx.Client(base_url=f'http://127.0.0.1:{api_port}',timeout=20) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code==200 and httpx.get(f'http://127.0.0.1:{inference_port}/health').status_code==200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError('Services failed to start')
                login=client.post('/api/auth/token',data={'username':'smoke-inspector','password':password})
                login.raise_for_status()
                client.headers['Authorization']='Bearer '+login.json()['access_token']
                image=io.BytesIO()
                Image.new('RGB',(320,240),'gray').save(image,'JPEG')
                meta={'captured_at':'2026-10-01T00:00:00Z','latitude':12.98,'longitude':77.6,
                      'gps_uncertainty_m':5,'road_name':'Synthetic HTTP smoke test'}
                response=client.post('/api/jobs',data={'metadata':json.dumps(meta)},headers={'Idempotency-Key':'image-smoke-001'},
                    files={'file':('image.jpg',image.getvalue(),'image/jpeg')})
                response.raise_for_status()
                jobs=[response.json()['id']]
                import cv2
                import numpy as np
                video=root/'video.avi'
                writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
                if not writer.isOpened():
                    raise RuntimeError('MJPG encoder unavailable')
                for _ in range(25):
                    writer.write(np.zeros((48,64,3),dtype=np.uint8))
                writer.release()
                video_meta={**meta,'gps_track':[{'offset_seconds':t,'latitude':12.98,'longitude':77.6,'uncertainty_m':5} for t in [0,3]]}
                response=client.post('/api/jobs',data={'metadata':json.dumps(video_meta)},headers={'Idempotency-Key':'video-smoke-001'},
                    files={'file':('video.avi',video.read_bytes(),'video/x-msvideo')})
                response.raise_for_status()
                jobs.append(response.json()['id'])
                for job_id in jobs:
                    for _ in range(100):
                        state=client.get('/api/jobs/'+job_id).json()
                        if state['status'] in {'completed','failed'}:
                            break
                        time.sleep(.2)
                    assert state['status']=='completed',state
                    assert state['model_info']['synthetic'] is True
                records=client.get('/api/defects').json()['items']
                assert len(records)==2,records
                assert all(d['synthetic'] for d in records)
                video_defect=next(d for d in records if d['job_id']==jobs[1])
                detail=client.get('/api/defects/'+video_defect['id']).json()
                assert len(detail['observations'])==2
                evidence=client.get('/api/observations/'+detail['observations'][0]['id']+'/image')
                assert evidence.status_code==200 and evidence.headers['content-type']=='image/jpeg'
                reviewed=client.patch('/api/defects/'+video_defect['id'],json={'status':'confirmed','note':'Smoke-test review',
                    'critical_location':True,'revision':video_defect['revision']})
                assert reviewed.status_code==200,reviewed.text
                assert client.get('/api/reports/defects.csv').status_code==200
                assert client.get('/api/defects?synthetic=false').json()['total']==0
                assert client.get('/api/users').status_code==403
                print(json.dumps({'status':'passed','image_jobs':1,'video_jobs':1,'canonical_defects':2,
                                  'video_observations':2,'evidence':'retrieved','review':'saved','export':'passed',
                                  'mode':'synthetic','database':'SQLite; PostGIS not exercised'}))
        except Exception:
            for stream in logs:
                stream.flush()
            for log in root.glob('service-*.log'):
                print(log.name,log.read_text()[-8000:],file=sys.stderr)
            raise
        finally:
            for process in processes:
                if os.name == 'nt':
                    # The Windows venv launcher can own a child python process.
                    # Stop the entire owned process tree before closing its log files.
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                else:
                    process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for stream in logs:
                stream.close()


if __name__=='__main__':
    main()


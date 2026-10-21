import json
import pytest
from sqlalchemy import select
from backend.app.models import AuditEvent, Defect, Job, Observation, User, now
from backend.app.cli import seed
from backend.app.security import issue_token

META={"captured_at":"2026-10-01T10:00:00Z","latitude":12.98,"longitude":77.60,"gps_uncertainty_m":5,"road_name":"Test road"}


def upload(client, headers, image, key="test-key-123", metadata=None):
    return client.post('/api/jobs',headers={**headers,'Idempotency-Key':key},
        data={'metadata':json.dumps(metadata or META)},files={'file':('road.jpg',image,'image/jpeg')})


def test_auth_rbac_revocation(client,auth,image_bytes):
    assert client.get('/api/defects').status_code==401
    viewer=auth('viewer')
    assert upload(client,viewer,image_bytes).status_code==403
    assert client.get('/api/users',headers=viewer).status_code==403
    assert client.get('/api/defects',headers=viewer).status_code==200
    assert client.post('/api/auth/logout',headers=viewer).status_code==200
    assert client.get('/api/auth/me',headers=viewer).status_code==401


def test_login_invalid_and_throttle(client):
    for _ in range(20):
        assert client.post('/api/auth/token',data={'username':'missing','password':'wrong'}).status_code==401
    assert client.post('/api/auth/token',data={'username':'missing','password':'wrong'}).status_code==429


def test_upload_idempotency_and_conflict(client,auth,image_bytes,factory):
    headers=auth('inspector')
    first=upload(client,headers,image_bytes)
    assert first.status_code==202,first.text
    second=upload(client,headers,image_bytes)
    assert first.json()['id']==second.json()['id']
    assert upload(client,headers,image_bytes,metadata={**META,'road_name':'different'}).status_code==409
    with factory() as db:
        assert len(db.scalars(select(Job)).all())==1


def test_upload_rejects_malformed(client,auth):
    response=upload(client,auth(),b'garbage')
    assert response.status_code==422


def test_upload_rejects_missing_gps(client,auth,image_bytes):
    assert upload(client,auth(),image_bytes,metadata={'captured_at':META['captured_at']}).status_code==422


def test_timezone_required(client,auth,image_bytes):
    assert upload(client,auth(),image_bytes,metadata={**META,'captured_at':'2026-10-01T10:00:00'}).status_code==422


def test_seed_filter_review_audit_and_csv(client,auth,factory):
    with factory() as db:
        assert seed(db)==36
        assert seed(db)==0
    headers=auth()
    data=client.get('/api/defects?synthetic=true&limit=10',headers=headers).json()
    assert data['total']==36 and len(data['items'])==10
    assert client.get('/api/defects?synthetic=false',headers=headers).json()['total']==0
    item=data['items'][0]
    update={'status':'confirmed','note':'Field review needed','critical_location':True,'revision':item['revision']}
    response=client.patch('/api/defects/'+item['id'],headers=headers,json=update)
    assert response.status_code==200,response.text
    assert response.json()['revision']==2
    assert client.patch('/api/defects/'+item['id'],headers=headers,json=update).status_code==409
    audit=client.get('/api/audit?entity_id='+item['id'],headers=headers).json()
    assert audit[0]['action']=='defect_reviewed'
    analytics=client.get('/api/analytics',headers=headers).json()
    assert analytics['total']==36 and analytics['observed_health'] is not None
    assert client.get('/api/analytics?synthetic=false',headers=headers).json()['observed_health'] is None
    csv=client.get('/api/reports/defects.csv',headers=headers)
    assert csv.status_code==200 and 'synthetic' in csv.text


def test_invalid_spatial_and_date_filters(client,auth):
    headers=auth()
    for query in ['bbox=bad','bbox=0,0,900,91','since=2026-01-01T00:00:00','min_severity=101']:
        assert client.get('/api/defects?'+query,headers=headers).status_code==422


def test_csv_formula_injection(client,auth,factory):
    with factory() as db:
        seed(db)
        d=db.scalar(select(Defect))
        d.road_name='=HYPERLINK("evil")'
        db.commit()
    response=client.get('/api/reports/defects.csv',headers=auth())
    assert "'=HYPERLINK" in response.text


def test_disable_user_revokes_existing_token(client,auth):
    viewer=auth('viewer')
    response=client.patch('/api/users/viewer',headers=auth(),json={'role':'viewer','enabled':False})
    assert response.status_code==200
    assert client.get('/api/auth/me',headers=viewer).status_code==401


def test_create_user_and_reject_duplicate(client,auth):
    headers=auth()
    body={'username':'new-inspector','password':'long-enough-password','role':'inspector'}
    assert client.post('/api/users',headers=headers,json=body).status_code==201
    assert client.post('/api/users',headers=headers,json=body).status_code==409


def test_merge_retains_observations_and_audit(client,auth,factory):
    with factory() as db:
        seed(db)
        defects=db.scalars(select(Defect).where(Defect.defect_class=='pothole').limit(2)).all()
        a,b=defects
        b.latitude,b.longitude=a.latitude,a.longitude
        ids=a.id,b.id
        db.commit()
    response=client.post('/api/defects/'+ids[0]+'/merge',headers=auth(),json={'target_id':ids[1],'revision':1,'reason':'Same defect confirmed by field inspector'})
    assert response.status_code==200,response.text
    with factory() as db:
        assert db.get(Defect,ids[0]).merged_into_id==ids[1]
        assert len(db.scalars(select(Observation).where(Observation.defect_id==ids[1])).all())==2


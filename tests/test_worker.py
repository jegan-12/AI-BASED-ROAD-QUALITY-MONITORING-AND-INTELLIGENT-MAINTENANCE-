import pytest
from datetime import timedelta
from sqlalchemy import select
from backend.app.models import Defect, Job, Observation, now
from backend.app.worker import claim_job, heartbeat, persist, process
from backend.app.schemas import Detection, InferenceResult
from backend.app.config import settings


def add_job(factory):
    with factory() as db:
        job=Job(owner_id='admin',idempotency_key='worker-test',sha256='a'*64,path='missing.jpg',kind='image',
                metadata_json={'captured_at':'2026-10-01T00:00:00Z','latitude':12,'longitude':77,'gps_uncertainty_m':5})
        db.add(job)
        db.commit()
        return job.id


def result():
    return InferenceResult(detections=[Detection(defect_class='pothole',confidence=.9,bbox=[.2,.2,.5,.5])],
        model_version='synthetic-test',model_sha256='a'*64,synthetic=True,latency_ms=2,provenance={'name':'synthetic test'})


def test_claim_lease_reclaim_and_fencing(factory):
    job_id=add_job(factory)
    _,old=claim_job(factory)
    assert claim_job(factory) is None
    with factory() as db:
        db.get(Job,job_id).lease_until=now()-timedelta(seconds=1)
        db.commit()
    _,new=claim_job(factory)
    assert old!=new
    with pytest.raises(RuntimeError):
        heartbeat(job_id,old,10,factory)
    with pytest.raises(RuntimeError):
        persist(job_id,old,[],factory)
    heartbeat(job_id,new,10,factory)


def test_duplicate_suppression_retains_observations(factory):
    job_id=add_job(factory)
    _,token=claim_job(factory)
    persist(job_id,token,[(0,0,(12,77,5),result()),(1,2,(12,77,5),result())],factory)
    with factory() as db:
        assert len(db.scalars(select(Defect)).all())==1
        assert len(db.scalars(select(Observation)).all())==2
        assert db.get(Job,job_id).status=='completed'
    with pytest.raises(RuntimeError):
        persist(job_id,token,[],factory)


def test_mixed_models_roll_back_all_detections(factory):
    job_id=add_job(factory)
    _,token=claim_job(factory)
    changed=result().model_copy(update={'model_version':'different'})
    with pytest.raises(ValueError):
        persist(job_id,token,[(0,0,(12,77,5),result()),(1,2,(12,77,5),changed)],factory)
    with factory() as db:
        assert db.scalar(select(Defect)) is None


def test_worker_failure_has_no_partial_records(factory):
    job_id=add_job(factory)
    _,token=claim_job(factory)
    process(job_id,token,factory)
    with factory() as db:
        assert db.get(Job,job_id).status=='failed'
        assert db.scalar(select(Defect)) is None


def test_expired_final_attempt_fails(factory):
    job_id=add_job(factory)
    with factory() as db:
        job=db.get(Job,job_id)
        job.status='processing';job.attempts=3;job.lease_until=now()-timedelta(seconds=1)
        db.commit()
    assert claim_job(factory) is None
    with factory() as db:
        assert db.get(Job,job_id).status=='failed'


def test_wrong_model_calibration_is_rejected(factory, tmp_path, monkeypatch):
    import json
    path=tmp_path/'calibration.json'
    path.write_text(json.dumps({'version':'test-cal','target':'expert_visual_severity_0_100',
        'knots':[[0,0],[100,100]],'dataset_sha256':'b'*64,'model_sha256':'c'*64,
        'scoring_policy':'visual-screening-v1','heldout_mae':2.0}))
    monkeypatch.setattr(settings(),'calibration_path',path)
    job_id=add_job(factory)
    _,token=claim_job(factory)
    with pytest.raises(ValueError,match='Calibration model hash'):
        persist(job_id,token,[(0,0,(12,77,5),result())],factory)
    with factory() as db:
        assert db.scalar(select(Defect)) is None


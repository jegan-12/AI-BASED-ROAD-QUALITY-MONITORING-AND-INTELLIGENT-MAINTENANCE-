"""Run against a disposable migrated DB, never a production database."""
import os
import pytest
from sqlalchemy import text
from backend.app.db import make_engine
from backend.app.models import User, Job, Defect, now
from sqlalchemy.orm import sessionmaker
from backend.app.worker import candidate, claim_job
from backend.app.schemas import Detection
from uuid import uuid4


@pytest.mark.postgis
def test_postgis_generated_location_and_distance():
    url=os.getenv('TEST_POSTGIS_URL')
    if not url:
        pytest.skip('TEST_POSTGIS_URL not configured')
    engine=make_engine(url)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT postgis_version()'))
        assert connection.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname='ix_defects_location'"))==1
        assert connection.scalar(text("SELECT ST_DWithin(ST_Point(77,12)::geography,ST_Point(77.00001,12)::geography,8)"))
        generated=connection.scalar(text("SELECT is_generated FROM information_schema.columns WHERE table_name='defects' AND column_name='location'"))
        assert generated=='ALWAYS'
    engine.dispose()


@pytest.mark.postgis
def test_spatial_candidate_and_queue_locking():
    url=os.getenv('TEST_POSTGIS_URL')
    if not url:
        pytest.skip('TEST_POSTGIS_URL not configured')
    engine=make_engine(url)
    factory=sessionmaker(engine,expire_on_commit=False)
    prefix=str(uuid4())
    ids=[]
    try:
        with factory() as db:
            user=User(username='integration-'+prefix,password_hash='unused',role='viewer')
            db.add(user);db.flush();user_id=user.id
            for i in range(2):
                job=Job(owner_id=user.id,idempotency_key=prefix+str(i),sha256='a'*64,path='synthetic-no-media',kind='image',metadata_json={})
                db.add(job);db.flush();ids.append(job.id)
            defect=Defect(job_id=ids[0],defect_class='pothole',confidence=.9,bbox=[.2,.2,.5,.5],latitude=12,longitude=77,
                          gps_uncertainty_m=5,captured_at=now(),severity=60,explanation={},model_version='synthetic-test',synthetic=True)
            db.add(defect);db.commit();defect_id=defect.id
            detection=Detection(defect_class='pothole',confidence=.9,bbox=[.2,.2,.5,.5])
            assert candidate(db,detection,12,77.00001,5,ids[1],True)==defect_id
            assert candidate(db,detection,13,78,5,ids[1],True) is None
            # A lock held by another session is skipped, not waited on.
            locked=db.get(Job,ids[0],with_for_update=True)
            claimed=claim_job(factory)
            assert claimed and claimed[0]==ids[1]
            db.rollback()
    finally:
        with engine.begin() as connection:
            if ids:
                connection.execute(Defect.__table__.delete().where(Defect.job_id.in_(ids)))
                connection.execute(Job.__table__.delete().where(Job.id.in_(ids)))
                connection.execute(User.__table__.delete().where(User.id==user_id))
        engine.dispose()


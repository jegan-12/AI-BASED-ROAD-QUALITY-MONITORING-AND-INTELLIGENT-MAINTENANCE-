import os
import subprocess
import sys
from sqlalchemy import create_engine, inspect, text


def test_frozen_migration_round_trip(tmp_path):
    url='sqlite:///'+str(tmp_path/'migrated.db')
    env={**os.environ,'DATABASE_URL':url}
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True,capture_output=True)
    engine=create_engine(url)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='0001'
        assert {'jobs','defects','observations','users','audit_events'}.issubset(inspect(connection).get_table_names())
    engine.dispose()
    subprocess.run([sys.executable,'-m','alembic','downgrade','base'],env=env,check=True,capture_output=True)
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True,capture_output=True)


def test_postgres_offline_migration_contains_geography():
    env={**os.environ,'DATABASE_URL':'postgresql+psycopg://unused:unused@localhost/unused'}
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head','--sql'],env=env,check=True,capture_output=True,text=True)
    assert 'geography(Point,4326)' in result.stdout
    assert 'USING GIST(location)' in result.stdout
    assert 'CREATE TABLE jobs' in result.stdout


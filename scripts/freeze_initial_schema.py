"""Development-time helper: freeze the initial schema; never run against a database."""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from alembic.migration import MigrationContext
from alembic.autogenerate import produce_migrations, render_python_code
from backend.app.db import Base
from backend.app import models

with create_engine('sqlite://').connect() as connection:
    migration=produce_migrations(MigrationContext.configure(connection),Base.metadata)
up=render_python_code(migration.upgrade_ops)
down=render_python_code(migration.downgrade_ops)
geography='''
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SELECT postgis_version()")
        op.execute("""ALTER TABLE defects ADD COLUMN location geography(Point,4326)
            GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography) STORED""")
        op.execute("CREATE INDEX ix_defects_location ON defects USING GIST(location)")
'''
header='''"""Frozen initial schema and PostGIS geography. Revision 0001."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
'''
Path('backend/migrations/versions/0001_initial.py').write_text(header+up+'\n'+geography+'\ndef downgrade():\n'+down+'\n')
dialect=postgresql.dialect()
sql=['-- Reference schema. Apply changes with Alembic, not this snapshot.\nCREATE EXTENSION IF NOT EXISTS postgis;']
for table in Base.metadata.sorted_tables:
    sql.append(str(CreateTable(table).compile(dialect=dialect))+';')
    sql.extend(str(CreateIndex(index).compile(dialect=dialect))+';' for index in table.indexes)
sql.append('ALTER TABLE defects ADD COLUMN location geography(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography) STORED;')
sql.append('CREATE INDEX ix_defects_location ON defects USING GIST(location);')
Path('docs/schema.sql').write_text('\n\n'.join(sql)+'\n')
print('Frozen migration and schema snapshot')


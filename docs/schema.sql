-- Reference schema. Apply changes with Alembic, not this snapshot.
CREATE EXTENSION IF NOT EXISTS postgis;


CREATE TABLE login_attempts (
	id VARCHAR(36) NOT NULL, 
	bucket VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_login_attempts_created_at ON login_attempts (created_at);

CREATE INDEX ix_login_attempts_bucket ON login_attempts (bucket);


CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	token_revision INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (role IN ('viewer','inspector','admin')), 
	UNIQUE (username)
)

;


CREATE TABLE audit_events (
	id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	action VARCHAR(40) NOT NULL, 
	details JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;

CREATE INDEX ix_audit_events_entity_id ON audit_events (entity_id);


CREATE TABLE jobs (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	path VARCHAR(200) NOT NULL, 
	kind VARCHAR(10) NOT NULL, 
	metadata_json JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	progress INTEGER NOT NULL, 
	attempts INTEGER NOT NULL, 
	lease_token VARCHAR(36), 
	lease_until TIMESTAMP WITH TIME ZONE, 
	error VARCHAR(100), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	inference_ms FLOAT, 
	model_info JSON, 
	PRIMARY KEY (id), 
	UNIQUE (owner_id, idempotency_key), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
)

;

CREATE INDEX ix_jobs_status ON jobs (status);


CREATE TABLE defects (
	id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	defect_class VARCHAR(40) NOT NULL, 
	confidence FLOAT NOT NULL, 
	bbox JSON NOT NULL, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	gps_uncertainty_m FLOAT NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	severity FLOAT NOT NULL, 
	explanation JSON NOT NULL, 
	model_version VARCHAR(120) NOT NULL, 
	synthetic BOOLEAN NOT NULL, 
	road_name VARCHAR(120) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	critical_location BOOLEAN NOT NULL, 
	note VARCHAR(2000) NOT NULL, 
	duplicate_candidate_id VARCHAR(36), 
	merged_into_id VARCHAR(36), 
	revision INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (latitude >= -90 AND latitude <= 90), 
	CHECK (longitude >= -180 AND longitude <= 180), 
	CHECK (severity >= 0 AND severity <= 100), 
	CHECK (confidence >= 0 AND confidence <= 1), 
	FOREIGN KEY(job_id) REFERENCES jobs (id), 
	FOREIGN KEY(duplicate_candidate_id) REFERENCES defects (id), 
	FOREIGN KEY(merged_into_id) REFERENCES defects (id)
)

;

CREATE INDEX ix_defects_synthetic ON defects (synthetic);

CREATE INDEX ix_defects_captured_at ON defects (captured_at);

CREATE INDEX ix_defects_status ON defects (status);

CREATE INDEX ix_defects_defect_class ON defects (defect_class);

CREATE INDEX ix_defects_job_id ON defects (job_id);


CREATE TABLE observations (
	id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	defect_id VARCHAR(36) NOT NULL, 
	frame_index INTEGER NOT NULL, 
	ordinal INTEGER NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	details JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (job_id, frame_index, ordinal), 
	FOREIGN KEY(job_id) REFERENCES jobs (id), 
	FOREIGN KEY(defect_id) REFERENCES defects (id)
)

;

CREATE INDEX ix_observations_job_id ON observations (job_id);

CREATE INDEX ix_observations_defect_id ON observations (defect_id);

ALTER TABLE defects ADD COLUMN location geography(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography) STORED;

CREATE INDEX ix_defects_location ON defects USING GIST(location);

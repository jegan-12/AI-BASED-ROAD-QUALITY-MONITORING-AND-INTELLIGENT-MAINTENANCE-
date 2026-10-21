from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('viewer','inspector','admin')"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    token_revision: Mapped[int] = mapped_column(Integer, default=0)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inference_ms: Mapped[float | None] = mapped_column(Float)
    model_info: Mapped[dict | None] = mapped_column(JSON)


class Defect(Base):
    __tablename__ = "defects"
    __table_args__ = (CheckConstraint("latitude >= -90 AND latitude <= 90"),
                     CheckConstraint("longitude >= -180 AND longitude <= 180"),
                     CheckConstraint("severity >= 0 AND severity <= 100"),
                     CheckConstraint("confidence >= 0 AND confidence <= 1"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    defect_class: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[list] = mapped_column(JSON)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    gps_uncertainty_m: Mapped[float] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    severity: Mapped[float] = mapped_column(Float)
    explanation: Mapped[dict] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(120))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    road_name: Mapped[str] = mapped_column(String(120), default="Unassigned road")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    critical_location: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(2000), default="")
    duplicate_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("defects.id"))
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("defects.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("job_id", "frame_index", "ordinal"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    defect_id: Mapped[str] = mapped_column(ForeignKey("defects.id"), index=True)
    frame_index: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


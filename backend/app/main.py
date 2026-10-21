import csv
import hashlib
import io
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuditEvent, Defect, Job, LoginAttempt, Observation, User, now
from .schemas import CaptureMetadata, DefectClass, MergeRequest, NewUser, ReviewUpdate, UserUpdate
from .schemas import AnalyticsResponse, DefectPage, DefectResponse, JobResponse, TokenResponse, UserResponse
from .scoring import priority, utc
from .security import DUMMY_HASH, current_user, issue_token, password_hash, require_roles
from .vision import preprocess, gps_at, distance_m

logger = logging.getLogger("roadscope")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(app):
    settings().validate_secrets()
    settings().media_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="RoadScope API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url="/api/redoc",
              description="Road defect screening. GPS represents camera position. Synthetic data is flagged.")
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(","),
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])


@app.middleware("http")
async def request_logging(request, call_next):
    request_id = str(uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"event": "request_failed", "request_id": request_id}))
        response = Response(json.dumps({"detail": "Internal error", "request_id": request_id}),
                            status_code=500, media_type="application/json")
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    logger.info(json.dumps({"event": "request", "request_id": request_id, "method": request.method,
                           "path": request.url.path, "status": response.status_code,
                           "duration_ms": round((time.perf_counter()-start)*1000, 1)}))
    return response


def audit(db, actor, entity, action, details):
    db.add(AuditEvent(actor_id=actor.id, entity_id=entity, action=action, details=details))


def user_json(user):
    return {"id": user.id, "username": user.username, "role": user.role, "enabled": user.enabled}


def defect_json(d):
    score, reasons = priority(d, now())
    return {"id": d.id, "job_id": d.job_id, "defect_class": d.defect_class, "confidence": d.confidence,
            "bbox": d.bbox, "latitude": d.latitude, "longitude": d.longitude,
            "gps_uncertainty_m": d.gps_uncertainty_m, "captured_at": utc(d.captured_at),
            "severity": d.severity, "explanation": d.explanation, "model_version": d.model_version,
            "synthetic": d.synthetic, "road_name": d.road_name, "status": d.status,
            "critical_location": d.critical_location, "note": d.note, "revision": d.revision,
            "duplicate_candidate_id": d.duplicate_candidate_id, "merged_into_id": d.merged_into_id,
            "priority": score, "priority_reasons": reasons}


def job_json(j):
    return {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress,
            "attempts": j.attempts, "error": j.error, "created_at": utc(j.created_at),
            "completed_at": utc(j.completed_at) if j.completed_at else None, "inference_ms": j.inference_ms,
            "model_info": j.model_info, "road_name": j.metadata_json.get("road_name"), "sha256": j.sha256}


@app.get("/api/health", tags=["operations"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "demo_mode": settings().demo_mode}


@app.post("/api/auth/token", response_model=TokenResponse, tags=["authentication"])
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Advisory lock serializes rate-limit checks for a source; do not trust X-Forwarded-For.
    source = request.client.host if request.client else "local"
    bucket = hashlib.sha256((source + "|" + form.username[:80].lower()).encode()).hexdigest()
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(bucket[:15], 16)})
    cutoff = now() - timedelta(minutes=15)
    count = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.bucket == bucket, LoginAttempt.created_at > cutoff))
    if count >= 20:
        raise HTTPException(429, "Too many login attempts. Try again in 15 minutes.", headers={"Retry-After": "900"})
    db.add(LoginAttempt(bucket=bucket))
    db.query(LoginAttempt).filter(LoginAttempt.created_at < cutoff).delete()
    db.commit()
    user = db.scalar(select(User).where(User.username == form.username))
    valid = len(form.password) <= 128 and password_hash.verify(form.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.enabled:
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": issue_token(user), "token_type": "bearer", "user": user_json(user)}


@app.get("/api/auth/me", response_model=UserResponse, tags=["authentication"])
def me(user=Depends(current_user)):
    return user_json(user)


@app.post("/api/auth/logout", tags=["authentication"])
def logout(user=Depends(current_user), db: Session = Depends(get_db)):
    user.token_revision += 1
    db.commit()
    return {"revoked": True}


@app.get("/api/users", response_model=list[UserResponse], tags=["administration"])
def users(user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return [user_json(u) for u in db.scalars(select(User).order_by(User.username))]


@app.post("/api/users", status_code=201, response_model=UserResponse, tags=["administration"])
def create_user(body: NewUser, actor=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    user = User(username=body.username, password_hash=password_hash.hash(body.password), role=body.role)
    db.add(user)
    try:
        db.flush()
        audit(db, actor, user.id, "user_created", {"username": user.username, "role": user.role})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username already exists")
    return user_json(user)


@app.patch("/api/users/{user_id}", response_model=UserResponse, tags=["administration"])
def change_user(user_id: str, body: UserUpdate, actor=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    if user_id == actor.id:
        raise HTTPException(409, "Use another administrator to change your own access")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    audit(db, actor, user.id, "user_access_changed", {"before": user_json(user), "after": body.model_dump()})
    user.role, user.enabled = body.role, body.enabled
    user.token_revision += 1
    db.commit()
    return user_json(user)


@app.post("/api/jobs", status_code=202, response_model=JobResponse, tags=["ingestion"])
async def upload(metadata: str = Form(..., max_length=1000000), file: UploadFile = File(...),
                 idempotency_key: str = Header(..., min_length=8, max_length=100),
                 user=Depends(require_roles("admin", "inspector")), db: Session = Depends(get_db)):
    try:
        meta = CaptureMetadata.model_validate_json(metadata)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid capture metadata; use UTC timestamps and valid coordinates")
    suffix = Path(file.filename or "").suffix.lower()
    kind = "image" if suffix in {".jpg", ".jpeg", ".png", ".webp"} else "video" if suffix in {".mp4", ".mov", ".avi"} else None
    if not kind:
        raise HTTPException(415, "Supported: JPEG, PNG, WebP, MP4, MOV, AVI")
    if kind == "image":
        try:
            gps_at(meta, 0)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    elif len(meta.gps_track) < 2 or meta.gps_track[0].offset_seconds != 0:
        raise HTTPException(422, "Video requires a GPS track starting at offset zero")
    settings().media_dir.mkdir(parents=True, exist_ok=True)
    filename = str(uuid4()) + suffix
    path = settings().media_dir / filename
    digest, size = hashlib.sha256(), 0
    try:
        with path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds configured size limit")
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise HTTPException(422, "Empty upload")
        if kind == "image":
            try:
                preprocess(path.read_bytes())
            except ValueError as exc:
                raise HTTPException(422, str(exc))
        existing = db.scalar(select(Job).where(Job.owner_id == user.id, Job.idempotency_key == idempotency_key))
        normalized = meta.model_dump(mode="json")
        if existing:
            if existing.sha256 != digest.hexdigest() or existing.metadata_json != normalized:
                raise HTTPException(409, "Idempotency key was used for different content")
            path.unlink(missing_ok=True)
            return job_json(existing)
        job = Job(owner_id=user.id, idempotency_key=idempotency_key, sha256=digest.hexdigest(),
                  path=filename, kind=kind, metadata_json=normalized)
        db.add(job)
        db.flush()
        audit(db, user, job.id, "upload_queued", {"kind": kind, "sha256": job.sha256})
        db.commit()
        return job_json(job)
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(409, "Concurrent upload with this idempotency key; retry with the same key")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@app.get("/api/jobs", response_model=list[JobResponse], tags=["ingestion"])
def jobs(limit: int = Query(50, ge=1, le=200), user=Depends(current_user), db: Session = Depends(get_db)):
    return [job_json(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit))]


@app.get("/api/jobs/{job_id}", response_model=JobResponse, tags=["ingestion"])
def get_job(job_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job_json(job)


@app.post("/api/jobs/{job_id}/retry", response_model=JobResponse, tags=["ingestion"])
def retry(job_id: str, user=Depends(require_roles("admin", "inspector")), db: Session = Depends(get_db)):
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "failed":
        raise HTTPException(409, "Only failed jobs can be retried")
    job.status, job.error, job.attempts, job.progress = "queued", None, 0, 0
    audit(db, user, job.id, "job_retried", {})
    db.commit()
    return job_json(job)


def filtered_query(defect_class=None, status=None, synthetic=None, min_severity=0, since=None, until=None, bbox=None):
    query = select(Defect).where(Defect.merged_into_id.is_(None), Defect.severity >= min_severity)
    for field, value in [(Defect.defect_class, defect_class), (Defect.status, status), (Defect.synthetic, synthetic)]:
        if value is not None:
            query = query.where(field == value)
    if since:
        query = query.where(Defect.captured_at >= since)
    if until:
        query = query.where(Defect.captured_at <= until)
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(","))
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "bbox must be west,south,east,north without crossing the antimeridian")
        query = query.where(Defect.longitude.between(west, east), Defect.latitude.between(south, north))
        # Latitude/longitude predicates also support SQLite unit tests.
        if settings().database_url.startswith("postgresql"):
            query = query.where(text("location && ST_MakeEnvelope(:w,:s,:e,:n,4326)::geography")).params(w=west,s=south,e=east,n=north)
    return query


def filters(defect_class: DefectClass | None = None, status: str | None = Query(None, pattern="^(new|confirmed|scheduled|repaired|rejected)$"),
            synthetic: bool | None = None, min_severity: float = Query(0, ge=0, le=100),
            since: datetime | None = None, until: datetime | None = None, bbox: str | None = None):
    if any(t is not None and t.tzinfo is None for t in (since, until)):
        raise HTTPException(422, "Filter timestamps require timezone offsets")
    if since and until and since > until:
        raise HTTPException(422, "Start time must precede end time")
    return filtered_query(defect_class, status, synthetic, min_severity, since, until, bbox)


@app.get("/api/defects", response_model=DefectPage, tags=["defects"])
def defects(query=Depends(filters), limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0),
            user=Depends(current_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Defect.severity.desc(), Defect.id).offset(offset).limit(limit)).all()
    return {"items": [defect_json(d) for d in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/defects/{defect_id}", response_model=DefectResponse, tags=["defects"])
def detail(defect_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    defect = db.get(Defect, defect_id)
    if not defect:
        raise HTTPException(404, "Defect not found")
    result = defect_json(defect)
    obs = db.scalars(select(Observation).where(Observation.defect_id == defect.id).order_by(Observation.captured_at).limit(200))
    result["observations"] = [{"id": o.id, "job_id": o.job_id, "frame_index": o.frame_index,
                               "captured_at": utc(o.captured_at), "details": o.details} for o in obs]
    return result


@app.get("/api/observations/{observation_id}/image", tags=["defects"])
def evidence(observation_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    observation = db.get(Observation, observation_id)
    if not observation:
        raise HTTPException(404, "Observation not found")
    job = db.get(Job, observation.job_id)
    path = settings().media_dir / Path(job.path).name
    if not path.is_file():
        raise HTTPException(404, "Original media unavailable (synthetic seed has no photograph)")
    if job.kind == "image":
        raw, _ = preprocess(path.read_bytes())
    else:
        import cv2
        cap = cv2.VideoCapture(str(path))
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, observation.details["offset_seconds"] * 1000)
            ok, frame = cap.read()
            if not ok:
                raise HTTPException(422, "Frame unavailable")
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise HTTPException(422, "Frame encoding failed")
            raw, _ = preprocess(encoded.tobytes())
        finally:
            cap.release()
    return Response(raw, media_type="image/jpeg")


@app.patch("/api/defects/{defect_id}", response_model=DefectResponse, tags=["defects"])
def review(defect_id: str, body: ReviewUpdate, user=Depends(require_roles("admin", "inspector")), db: Session = Depends(get_db)):
    defect = db.scalar(select(Defect).where(Defect.id == defect_id).with_for_update())
    if not defect:
        raise HTTPException(404, "Defect not found")
    if defect.revision != body.revision or defect.merged_into_id:
        raise HTTPException(409, "Record changed; reload before reviewing")
    audit(db, user, defect.id, "defect_reviewed", {"before": {"status": defect.status, "note": defect.note,
          "critical_location": defect.critical_location}, "after": body.model_dump()})
    defect.status, defect.note, defect.critical_location = body.status, body.note, body.critical_location
    defect.revision += 1
    db.commit()
    return defect_json(defect)


@app.post("/api/defects/{defect_id}/merge", response_model=DefectResponse, tags=["defects"])
def merge(defect_id: str, body: MergeRequest, user=Depends(require_roles("admin", "inspector")), db: Session = Depends(get_db)):
    records = db.scalars(select(Defect).where(Defect.id.in_([defect_id, body.target_id])).order_by(Defect.id).with_for_update()).all()
    lookup = {d.id: d for d in records}
    source, target = lookup.get(defect_id), lookup.get(body.target_id)
    if not source or not target:
        raise HTTPException(404, "Defect not found")
    if source.id == target.id or source.revision != body.revision or source.merged_into_id or target.merged_into_id:
        raise HTTPException(409, "Invalid or stale merge")
    if source.synthetic != target.synthetic or source.defect_class != target.defect_class:
        raise HTTPException(422, "Merge requires the same data source and defect class")
    if distance_m(source.latitude, source.longitude, target.latitude, target.longitude) > 50:
        raise HTTPException(422, "Merge requires positions within 50 metres")
    source.merged_into_id, source.revision = target.id, source.revision + 1
    target.revision += 1
    db.query(Observation).filter(Observation.defect_id == source.id).update({"defect_id": target.id})
    audit(db, user, source.id, "defect_merged", {"target_id": target.id, "reason": body.reason})
    db.commit()
    return defect_json(target)


@app.get("/api/analytics", response_model=AnalyticsResponse, tags=["reporting"])
def analytics(query=Depends(filters), user=Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(query).all()
    active = [d for d in rows if d.status in {"new", "confirmed", "scheduled"}]
    return {"total": len(rows), "active": len(active), "synthetic": sum(d.synthetic for d in rows),
            "high_severity": sum(d.severity >= 65 for d in active),
            "observed_health": round(100-sum(d.severity for d in active)/len(active), 1) if active else None,
            "health_method": "100 - mean active visual severity; not PCI; coverage unknown",
            "by_class": {c: sum(d.defect_class == c for d in rows) for c in sorted({d.defect_class for d in rows})},
            "by_status": {s: sum(d.status == s for d in rows) for s in sorted({d.status for d in rows})},
            "by_day": {day: sum(d.captured_at.date().isoformat() == day for d in rows)
                       for day in sorted({d.captured_at.date().isoformat() for d in rows})},
            "priorities": [defect_json(d) for d in sorted(active, key=lambda d: priority(d, now())[0], reverse=True)[:10]]}


def csv_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


@app.get("/api/reports/defects.csv", tags=["reporting"])
def report(query=Depends(filters), user=Depends(current_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    if count > 50000:
        raise HTTPException(422, "Narrow filters to at most 50,000 records")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    fields = ["id", "road_name", "defect_class", "status", "severity", "confidence", "latitude", "longitude",
              "gps_uncertainty_m", "captured_at", "synthetic", "model_version", "priority"]
    writer.writerow(fields)
    for defect in db.scalars(query.order_by(Defect.captured_at.desc())):
        data = defect_json(defect)
        writer.writerow([csv_safe(data[k]) for k in fields])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=roadscope-defects.csv"})


@app.get("/api/audit", tags=["administration"])
def events(entity_id: str | None = None, user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)
    if entity_id:
        query = select(AuditEvent).where(AuditEvent.entity_id == entity_id).order_by(AuditEvent.created_at.desc()).limit(200)
    return [{"id": e.id, "actor_id": e.actor_id, "entity_id": e.entity_id, "action": e.action,
             "details": e.details, "created_at": e.created_at} for e in db.scalars(query)]


@app.get("/api/model", tags=["operations"])
def model(user=Depends(current_user)):
    try:
        response = httpx.get(settings().inference_url + "/model", timeout=5,
                             headers={"X-API-Key": settings().internal_api_key})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return {"status": "unavailable", "metrics": None, "message": "Inference service unavailable"}


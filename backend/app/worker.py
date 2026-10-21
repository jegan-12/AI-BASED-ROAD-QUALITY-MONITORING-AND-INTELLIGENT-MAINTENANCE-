"""Durable database queue; run: python -m backend.app.worker."""
import json
import logging
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import or_, select, text, update
from .config import settings
from .db import SessionLocal
from .models import Defect, Job, Observation, now
from .schemas import CaptureMetadata, InferenceResult
from .scoring import load_calibration, severity
from .vision import distance_m, frames, nms, same_observation

logger = logging.getLogger("roadscope.worker")
logging.basicConfig(level=logging.INFO, format="%(message)s")
LEASE_SECONDS = 120


def claim_job(factory=SessionLocal):
    with factory() as db, db.begin():
        # Poisoned leases eventually fail instead of remaining queued forever.
        db.execute(update(Job).where(Job.status == "processing", Job.lease_until < now(), Job.attempts >= 3)
                   .values(status="failed", error="worker_lease_expired", lease_token=None))
        job = db.scalar(select(Job).where(Job.attempts < 3,
            or_(Job.status == "queued", (Job.status == "processing") & (Job.lease_until < now())))
            .order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return None
        job.status, job.lease_token = "processing", str(uuid4())
        job.lease_until, job.attempts = now() + timedelta(seconds=LEASE_SECONDS), job.attempts + 1
        job.error, job.progress = None, 0
        return job.id, job.lease_token


def heartbeat(job_id, token, progress, factory=SessionLocal):
    with factory() as db, db.begin():
        result = db.execute(update(Job).where(Job.id == job_id, Job.lease_token == token, Job.status == "processing")
            .values(lease_until=now()+timedelta(seconds=LEASE_SECONDS), progress=min(95, progress)))
        if result.rowcount != 1:
            raise RuntimeError("Job lease lost")


def candidate(db, detection, lat, lon, uncertainty, job_id, synthetic):
    if uncertainty > 15:
        return None
    query = select(Defect).where(Defect.job_id != job_id, Defect.defect_class == detection.defect_class,
        Defect.synthetic == synthetic, Defect.merged_into_id.is_(None), Defect.gps_uncertainty_m <= 15,
        Defect.status.in_(["new", "confirmed", "scheduled"]))
    if db.bind.dialect.name == "postgresql":
        query = query.where(text("ST_DWithin(location, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, 8)"))
        query = query.params(lon=lon, lat=lat)
    for existing in db.scalars(query.order_by(Defect.captured_at.desc()).limit(500)):
        if distance_m(lat, lon, existing.latitude, existing.longitude) <= 8:
            return existing.id
    return None


def persist(job_id, token, batches, factory=SessionLocal):
    calibration = load_calibration(settings().calibration_path)
    with factory() as db, db.begin():
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job.status != "processing" or job.lease_token != token:
            raise RuntimeError("Job lease lost")
        meta = CaptureMetadata.model_validate(job.metadata_json)
        previous = []
        latency = 0
        identity = None
        for index, offset, position, result in batches:
            current_identity = (result.model_version, result.model_sha256, result.synthetic)
            if identity and current_identity != identity:
                raise ValueError("Model changed during job")
            identity = current_identity
            if calibration and calibration["model_sha256"] != result.model_sha256:
                raise ValueError("Calibration model hash does not match inference model")
            if result.synthetic and not settings().demo_mode:
                raise ValueError("Synthetic result rejected in real deployment")
            latency += result.latency_ms
            lat, lon, uncertainty = position
            captured = meta.captured_at + timedelta(seconds=offset)
            used = set()
            current = []
            for ordinal, detection in enumerate(nms(result.detections, settings().confidence_threshold, settings().nms_iou)):
                match = next((p for p in reversed(previous) if p["id"] not in used and
                              same_observation(p, detection, lat, lon, uncertainty, offset)), None)
                if match:
                    defect_id = match["id"]
                    used.add(defect_id)
                else:
                    score, explanation = severity(detection, calibration)
                    explanation["model_sha256"] = result.model_sha256
                    explanation["provenance"] = result.provenance
                    defect = Defect(job_id=job.id, defect_class=detection.defect_class,
                        confidence=detection.confidence, bbox=detection.bbox, latitude=lat, longitude=lon,
                        gps_uncertainty_m=uncertainty, captured_at=captured, severity=score,
                        explanation=explanation, model_version=result.model_version, synthetic=result.synthetic,
                        road_name=meta.road_name,
                        duplicate_candidate_id=candidate(db, detection, lat, lon, uncertainty, job.id, result.synthetic))
                    db.add(defect)
                    db.flush()
                    defect_id = defect.id
                db.add(Observation(job_id=job.id, defect_id=defect_id, frame_index=index, ordinal=ordinal,
                    captured_at=captured, details={**detection.model_dump(), "latitude": lat, "longitude": lon,
                    "gps_uncertainty_m": uncertainty, "offset_seconds": offset,
                    "association": "temporal_spatial_box_match" if match else "new",
                    "synthetic": result.synthetic, "model_version": result.model_version}))
                current.append({"id": defect_id, "class": detection.defect_class, "bbox": detection.bbox,
                                "lat": lat, "lon": lon, "uncertainty": uncertainty, "offset": offset})
            previous = [p for p in previous if offset-p["offset"] <= 5 and p["id"] not in used] + current
        job.status, job.progress, job.completed_at = "completed", 100, now()
        job.lease_token, job.lease_until, job.inference_ms = None, None, latency
        job.model_info = {"version": identity[0], "sha256": identity[1], "synthetic": identity[2]} if identity else None


def process(job_id, token, factory=SessionLocal):
    try:
        with factory() as db:
            job = db.get(Job, job_id)
            meta = CaptureMetadata.model_validate(job.metadata_json)
            path = settings().media_dir / Path(job.path).name
            kind = job.kind
        batches = []
        with httpx.Client(timeout=60, headers={"X-API-Key": settings().internal_api_key}) as client:
            for index, offset, raw, position in frames(path, kind, meta, settings()):
                heartbeat(job_id, token, int(index/settings().max_frames*90), factory)
                response = client.post(settings().inference_url+"/predict", files={"file": ("frame.jpg", raw, "image/jpeg")})
                response.raise_for_status()
                batches.append((index, offset, position, InferenceResult.model_validate(response.json())))
                heartbeat(job_id, token, int((index+1)/settings().max_frames*90), factory)
        persist(job_id, token, batches, factory)
        logger.info(json.dumps({"event": "job_completed", "job_id": job_id, "frames": len(batches)}))
    except Exception as exc:
        transient = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or (
            isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500)
        code = "inference_unavailable" if transient else "invalid_media_or_result" if isinstance(exc, ValueError) else "processing_failed"
        with factory() as db, db.begin():
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job and job.lease_token == token:
                job.status = "queued" if transient and job.attempts < 3 else "failed"
                job.error, job.lease_token, job.lease_until = code, None, None
        logger.exception(json.dumps({"event": "job_failed", "job_id": job_id, "code": code}))


def main():
    settings().validate_secrets()
    while True:
        try:
            claimed = claim_job()
            if claimed:
                process(*claimed)
            else:
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception(json.dumps({"event": "worker_loop_error"}))
            time.sleep(5)


if __name__ == "__main__":
    main()


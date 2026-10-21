import argparse
import getpass
import hashlib
import random
from datetime import timedelta
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import Defect, Job, Observation, User, now
from .schemas import CLASSES, Detection, NewUser
from .scoring import severity
from .security import password_hash


def seed(db):
    if not settings().demo_mode:
        raise RuntimeError("Seeding requires DEMO_MODE=true")
    user = db.scalar(select(User).where(User.role == "admin"))
    if not user:
        raise RuntimeError("Create an administrator first")
    if db.scalar(select(Job).where(Job.idempotency_key == "synthetic-seed-v1")):
        return 0
    job = Job(owner_id=user.id, idempotency_key="synthetic-seed-v1", sha256=hashlib.sha256(b"seed-v1").hexdigest(),
              path="synthetic-no-media", kind="image", metadata_json={"road_name": "Synthetic Bengaluru survey"},
              status="completed", progress=100, completed_at=now(),
              model_info={"version": "synthetic-seed-v1", "synthetic": True})
    db.add(job)
    db.flush()
    rng = random.Random(42)
    roads = ["MG Road", "Residency Road", "Richmond Road", "Cubbon Road", "Brigade Road", "Lavelle Road"]
    for i in range(36):
        cls = CLASSES[i % len(CLASSES)]
        width, height = rng.uniform(.1, .48), rng.uniform(.08, .4)
        detection = Detection(defect_class=cls, confidence=round(rng.uniform(.52, .96), 2), bbox=[.2, .35, .2+width, .35+height])
        score, explanation = severity(detection)
        explanation["provenance"] = {"name": "Seeded synthetic demonstration", "real_data": False, "seed": 42}
        defect = Defect(job_id=job.id, defect_class=cls, confidence=detection.confidence, bbox=detection.bbox,
            latitude=12.968+rng.uniform(0, .025), longitude=77.585+rng.uniform(0, .035), gps_uncertainty_m=8,
            captured_at=now()-timedelta(days=i % 14), severity=score, explanation=explanation,
            model_version="synthetic-seed-v1", synthetic=True, road_name=roads[i % 6],
            status=["new", "confirmed", "scheduled", "new", "repaired", "new"][i % 6], critical_location=i % 7 == 0)
        db.add(defect)
        db.flush()
        db.add(Observation(job_id=job.id, defect_id=defect.id, frame_index=i, ordinal=0,
            captured_at=defect.captured_at, details={**detection.model_dump(), "synthetic": True, "offset_seconds": 0}))
    db.commit()
    return 36


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-admin", "seed"])
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "seed":
            print(f"Created {seed(db)} synthetic defects")
        else:
            if db.scalar(select(User).where(User.username == args.username)):
                raise SystemExit("Account already exists")
            password = getpass.getpass("Administrator password (12+ characters): ")
            NewUser(username=args.username, password=password, role="admin")
            db.add(User(username=args.username, password_hash=password_hash.hash(password), role="admin"))
            db.commit()
            print("Administrator created")


if __name__ == "__main__":
    main()


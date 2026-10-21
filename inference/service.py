import hashlib
import io
import json
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File
from PIL import Image
from backend.app.config import settings
from backend.app.schemas import CLASSES, Detection, InferenceResult
from backend.app.vision import preprocess, nms


class ModelAdapter:
    def __init__(self):
        self.model = None
        self.lock = threading.Lock()
        self.card = {"status": "disabled", "metrics": None, "version": None}
        self.digest = ""
        mode = settings().inference_mode
        if mode == "demo":
            self.card = {"status": "ready", "version": "synthetic-fixture-v1", "synthetic": True,
                         "metrics": None, "dataset": {"name": "Deterministic synthetic fixture", "real_data": False},
                         "limitations": ["Outputs are fixtures independent of image content; not a trained model"]}
            self.digest = hashlib.sha256(b"synthetic-fixture-v1").hexdigest()
        elif mode == "yolo":
            card_path = settings().model_card
            self.card = json.loads(card_path.read_text())
            weights = (card_path.parent / self.card["weights"]).resolve()
            self.digest = hashlib.sha256(weights.read_bytes()).hexdigest()
            if self.digest != self.card["sha256"]:
                raise ValueError("Model weight hash mismatch")
            if not self.card.get("dataset", {}).get("provenance") or not self.card.get("version"):
                raise ValueError("Model card requires dataset provenance and version")
            self.mapping = self.card["class_mapping"]
            if not self.mapping or any(v not in CLASSES for v in self.mapping.values()):
                raise ValueError("Invalid road class mapping")
            from ultralytics import YOLO
            self.model = YOLO(str(weights))
            if set(self.mapping) != {str(v) for v in self.model.names.values()}:
                raise ValueError("All model classes must be explicitly mapped; generic COCO weights are unsuitable")
            self.card.update(status="ready", synthetic=False)
        elif mode != "disabled":
            raise ValueError("INFERENCE_MODE must be disabled, demo or yolo")

    def predict(self, raw):
        if self.card["status"] != "ready":
            raise HTTPException(503, "No road-specific model registered")
        started = time.perf_counter()
        normalized, _ = preprocess(raw)
        if self.card.get("synthetic"):
            detections = [Detection(defect_class="pothole", confidence=0.88, bbox=[0.3, 0.45, 0.62, 0.78])]
        else:
            with self.lock:
                result = self.model.predict(Image.open(io.BytesIO(normalized)), imgsz=640,
                    conf=settings().confidence_threshold, iou=settings().nms_iou, max_det=300,
                    retina_masks=True, verbose=False)[0]
            detections = []
            for index, box in enumerate(result.boxes):
                area = float(result.masks.data[index].float().mean().item()) if result.masks is not None else None
                coords = [max(0.0, min(1.0, float(x))) for x in box.xyxyn[0].tolist()]
                if coords[0] >= coords[2] or coords[1] >= coords[3]:
                    continue
                detections.append(Detection(defect_class=self.mapping[result.names[int(box.cls.item())]],
                    confidence=float(box.conf.item()), bbox=coords, mask_area_ratio=area))
        return InferenceResult(detections=nms(detections, settings().confidence_threshold, settings().nms_iou),
            model_version=self.card["version"], model_sha256=self.digest,
            synthetic=self.card.get("synthetic", False), latency_ms=(time.perf_counter()-started)*1000,
            provenance=self.card["dataset"])


adapter = None


@asynccontextmanager
async def lifespan(app):
    global adapter
    settings().validate_secrets()
    adapter = ModelAdapter()
    yield


app = FastAPI(title="RoadScope internal inference", version="1.0.0", lifespan=lifespan)


def authenticate(x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, settings().internal_api_key):
        raise HTTPException(401, "Invalid service key")


@app.get("/health")
def health():
    return {"status": "ok", "model_status": adapter.card["status"]}


@app.get("/model", dependencies=[Depends(authenticate)])
def model():
    return {k: v for k, v in adapter.card.items() if k != "weights"}


@app.post("/predict", response_model=InferenceResult, dependencies=[Depends(authenticate)])
def predict(file: UploadFile = File(...)):
    try:
        raw = file.file.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(413, "Frame exceeds 10 MB")
        return adapter.predict(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        file.file.close()


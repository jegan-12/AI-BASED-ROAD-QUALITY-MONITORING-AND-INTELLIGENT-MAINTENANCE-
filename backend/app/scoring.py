import json
from datetime import timezone
from pathlib import Path

CLASS_BASE = {"pothole": 40, "longitudinal_crack": 18, "transverse_crack": 22,
              "alligator_cracking": 35, "rutting": 30, "other": 15}


def load_calibration(path: Path | None):
    if not path:
        return None
    data = json.loads(path.read_text())
    pairs = data["knots"]
    if len(pairs) < 2 or not data.get("dataset_sha256") or not data.get("version"):
        raise ValueError("Calibration requires knots, version and dataset provenance")
    if data.get("target") != "expert_visual_severity_0_100" or not isinstance(data.get("heldout_mae"), (float, int)):
        raise ValueError("Calibration must include a held-out evaluation")
    if len(data.get("model_sha256", "")) != 64 or data.get("scoring_policy") != "visual-screening-v1":
        raise ValueError("Calibration must be bound to the model hash and scoring policy")
    if any(not (0 <= x <= 100 and 0 <= y <= 100) for x, y in pairs):
        raise ValueError("Calibration outside score bounds")
    if any(b[0] <= a[0] or b[1] < a[1] for a, b in zip(pairs, pairs[1:])):
        raise ValueError("Calibration must be monotonic")
    return data


def severity(detection, calibration=None):
    x1, y1, x2, y2 = detection.bbox
    area = detection.mask_area_ratio
    area_source = "mask" if area is not None else "bounding_box_proxy"
    area = area if area is not None else (x2 - x1) * (y2 - y1)
    raw = min(100.0, CLASS_BASE[detection.defect_class] + min(60.0, area * 240))
    value = raw
    if calibration:
        knots = calibration["knots"]
        value = knots[0][1] if raw <= knots[0][0] else knots[-1][1]
        for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
            if x0 <= raw <= x1:
                value = y0 + (raw - x0) / (x1 - x0) * (y1 - y0)
                break
    return round(value, 2), {"policy": "visual-screening-v1", "raw_score": round(raw, 2),
        "class_base": CLASS_BASE[detection.defect_class], "image_area_ratio": round(area, 6),
        "area_source": area_source, "calibration_version": calibration["version"] if calibration else None,
        "calibration_dataset_sha256": calibration["dataset_sha256"] if calibration else None,
        "measurement": "image-relative; not physical dimensions", "confidence_used_in_severity": False}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def priority(defect, at):
    age = max(0, (utc(at) - utc(defect.captured_at)).total_seconds() / 86400)
    parts = {"severity": round(0.75 * defect.severity, 2),
             "age": round(min(15, age / 30 * 15), 2),
             "critical_location": 10 if defect.critical_location else 0}
    return round(sum(parts.values()), 2), parts


"""Validate a provenance manifest, train a detector, evaluate, and emit a deployable model card."""
import argparse
import hashlib
import json
import platform
import shutil
import statistics
import time
from pathlib import Path
from backend.app.schemas import CLASSES
from backend.app.vision import preprocess
from .metrics import match_counts, summarize


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_manifest(path):
    data = json.loads(path.read_text())
    if not data.get("samples") or not data.get("provenance") or not data.get("license") or "REPLACE" in data["license"]:
        raise ValueError("Provide labeled samples, provenance and a verified license")
    if not data.get("classes") or any(c not in CLASSES for c in data["classes"]):
        raise ValueError("Unsupported class taxonomy")
    hashes, groups, splits = {}, {}, set()
    for sample in data["samples"]:
        split, group = sample["split"], sample["route_group"]
        if split not in {"train", "val", "test"} or not group:
            raise ValueError("Each sample needs train/val/test split and route_group")
        splits.add(split)
        if group in groups and groups[group] != split:
            raise ValueError("Route group leakage across splits")
        groups[group] = split
        image, label = path.parent / sample["image"], path.parent / sample["label"]
        digest = sha(image)
        if digest in hashes:
            raise ValueError("Duplicate image content in dataset")
        hashes[digest] = split
        if digest != sample["sha256"] or sha(label) != sample["label_sha256"]:
            raise ValueError("Dataset content hash mismatch")
        from PIL import Image
        with Image.open(image) as source:
            if source.getexif().get(274, 1) != 1:
                raise ValueError("Normalize EXIF orientation and update labels before training")
        preprocess(image.read_bytes())
        for row in label.read_text().splitlines():
            values = list(map(float, row.split()))
            if len(values) != 5:
                raise ValueError("Training pipeline currently requires YOLO detection boxes: class cx cy w h")
            cls, x, y, w, h = values
            if int(cls) != cls or not (0 <= cls < len(data["classes"])):
                raise ValueError("Label class outside taxonomy")
            if not (0 < w <= 1 and 0 < h <= 1 and w/2 <= x <= 1-w/2 and h/2 <= y <= 1-h/2):
                raise ValueError("Invalid normalized label bounds")
    if splits != {"train", "val", "test"}:
        raise ValueError("All three route-disjoint splits are required")
    return data


def prepare(manifest, output):
    data = audit_manifest(manifest)
    target = output / "dataset"
    if target.exists():
        raise ValueError("Use a fresh output directory to avoid stale dataset samples")
    for i, sample in enumerate(data["samples"]):
        split = sample["split"]
        image = manifest.parent / sample["image"]
        for folder in ("images", "labels"):
            (target / folder / split).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target / "images" / split / f"{i}{image.suffix.lower()}")
        shutil.copyfile(manifest.parent / sample["label"], target / "labels" / split / f"{i}.txt")
    # JSON is valid YAML; avoid manual YAML quoting and absolute-path escaping bugs.
    config = {"path": str(target.resolve()), "train": "images/train", "val": "images/val", "test": "images/test",
              "names": dict(enumerate(data["classes"]))}
    config_path = output / "dataset.yaml"
    config_path.write_text(json.dumps(config, indent=2))
    return data, config_path


def evaluate(model, config, output, data, manifest, device):
    import ultralytics
    metrics = model.val(data=str(config), split="test", imgsz=640, conf=0.001, iou=0.6, device=device,
                        plots=True, project=str(output), name="heldout", exist_ok=False)
    per_class = []
    for metric_index, class_id in enumerate(metrics.box.ap_class_index.tolist()):
        p, r, map50, map95 = metrics.box.class_result(metric_index)
        per_class.append({"class": data["classes"][class_id], "precision": float(p), "recall": float(r),
                          "mAP50": float(map50), "mAP50_95": float(map95)})
    latencies = []
    counts = {name: {"tp": 0, "fp": 0, "fn": 0} for name in data["classes"]}
    import io
    from PIL import Image
    for sample in [s for s in data["samples"] if s["split"] == "test"]:
        raw = (manifest.parent / sample["image"]).read_bytes()
        started = time.perf_counter()
        normalized, _ = preprocess(raw)
        result = model.predict(Image.open(io.BytesIO(normalized)), imgsz=640, conf=.35, iou=.5,
                               device=device, verbose=False)[0]
        latencies.append((time.perf_counter()-started)*1000)
        predictions = [{"class": result.names[int(box.cls.item())], "confidence": float(box.conf.item()),
                        "bbox": box.xyxyn[0].tolist()} for box in result.boxes]
        truths = []
        for row in (manifest.parent / sample["label"]).read_text().splitlines():
            cls, x, y, width, height = map(float, row.split())
            truths.append({"class": data["classes"][int(cls)],
                           "bbox": [x-width/2, y-height/2, x+width/2, y+height/2]})
        sample_counts = match_counts(predictions, truths, data["classes"])
        for name, values in sample_counts.items():
            for key, value in values.items():
                counts[name][key] += value
    report = {"split": "test", "mAP50": float(metrics.box.map50), "mAP50_95": float(metrics.box.map),
        "class_metrics": per_class, "operating_confidence": .35,
        "fixed_operating_point": {"confidence": .35, "match_iou": .5, "nms_iou": .5,
                                  "class_metrics": summarize(counts)},
        "precision_recall_note": "Ultralytics per-class P/R at selected F1 operating point; not fixed 0.35. See heldout PR curves.",
        "latency": {"samples": len(latencies), "mean_ms": statistics.mean(latencies),
                    "p95_ms": sorted(latencies)[max(0, int(len(latencies)*.95)-1)], "includes_cold_start": True,
                    "scope": "preprocess + predict; excludes HTTP and database"},
        "hardware": platform.platform(), "device": device, "ultralytics": ultralytics.__version__,
        "dataset_sha256": sha(manifest)}
    (output / "evaluation.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["audit", "train", "evaluate"])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("ml/runs/road-v1"))
    parser.add_argument("--weights", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--version", default="road-v1")
    args = parser.parse_args()
    data = audit_manifest(args.manifest)
    if args.command == "audit":
        print(json.dumps({"samples": len(data["samples"]), "manifest_sha256": sha(args.manifest), "status": "valid"}))
        return
    args.output.mkdir(parents=True, exist_ok=True)
    data, config = prepare(args.manifest, args.output)
    from ultralytics import YOLO
    model = YOLO(args.weights)
    base_weights_hash = sha(model.ckpt_path)
    if args.command == "train":
        model.train(data=str(config), epochs=args.epochs, imgsz=640, seed=args.seed, deterministic=True,
                    device=args.device, workers=0, project=str(args.output), name="train", exist_ok=False)
        model = YOLO(str(Path(model.trainer.best)))
    metrics = evaluate(model, config, args.output, data, args.manifest, args.device)
    destination = args.output / "model.pt"
    shutil.copyfile(model.ckpt_path, destination)
    card = {"version": args.version, "weights": "model.pt", "sha256": sha(destination),
        "class_mapping": {name: name for name in data["classes"]},
        "dataset": {"name": data["name"], "provenance": data["provenance"], "license": data["license"],
                    "manifest_sha256": sha(args.manifest)}, "metrics": metrics,
        "training": {"seed": args.seed, "epochs": args.epochs, "base_weights": args.weights,
                     "base_weights_sha256": base_weights_hash,
                     "python": platform.python_version(), "deterministic": True},
        "limitations": ["No depth or physical dimensions", "Route-specific domain shift requires validation",
                        "Rutting requires field confirmation", "Class absence in held-out data means unevaluated"]}
    (args.output / "model-card.json").write_text(json.dumps(card, indent=2))
    print(f"Model card: {args.output / 'model-card.json'}")


if __name__ == "__main__":
    main()


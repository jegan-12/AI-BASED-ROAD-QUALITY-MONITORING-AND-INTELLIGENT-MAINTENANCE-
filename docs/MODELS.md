# Model, evaluation and calibration workflow

## Data acquisition and provenance

No real images, labels or pretrained road model are bundled or silently downloaded. A potential public starting point is [RDD2022, by the dataset authors](https://github.com/sekilab/RoadDamageDetector). Its road-damage taxonomy does not establish full coverage of rutting or every other visible condition. Verify license, class definitions and local collection rights before use. Add locally labeled examples for missing classes. Include geographic diversity, day/night, weather, road surfaces, camera setups, blur and negative images. Independently adjudicate ambiguous labels.

Each dataset manifest includes a name, provenance, verified license, supported classes and samples. Every sample contains `image`, `label`, `sha256`, `label_sha256`, `route_group` and `split` (train/val/test). Paths are relative to the manifest. Labels use standard YOLO `class center_x center_y width height`, normalized to [0,1]. Empty label files represent negative images. Orient images before labeling. Label boxes must remain in frame. The audit checks file hashes, bounds, taxonomy, EXIF orientation, duplicate images and route-disjoint splits. Route groups should include adjacent drives and dates where overlap creates leakage. Exact hash checks do not detect perceptual near-duplicates; review those during dataset preparation.

Example sample (replace all placeholder values with actual files and hashes):

```json
{"image":"images/001.jpg","label":"labels/001.txt","sha256":"actual image hash",
 "label_sha256":"actual label hash","route_group":"cityA-route17",
 "split":"train"}
```

## Training and evaluation

Install the optional model dependency in an isolated environment:

```sh
python -m pip install ultralytics==8.3.114
python -m ml.pipeline audit --manifest datasets/roads/manifest.json
python -m ml.pipeline train --manifest datasets/roads/manifest.json --output ml/runs/road-v1 --weights yolo11n.pt --epochs 100 --seed 42 --device cpu --version road-v1
```

YOLO11n is a compact transfer-learning baseline; COCO initialization is not a road detector. The first training run may download initialization weights. Use a pre-provisioned local weight path for offline reproduction. The initial pipeline trains bounding-box detection. The service also supports externally trained Ultralytics segmentation weights, but the manifest training command intentionally rejects segmentation labels instead of misinterpreting them.

Expected outputs: staged dataset and dataset.yaml; trained weights; held-out validation plots; evaluation.json with class-wise precision/recall, mAP50, mAP50–95 and measured inference latency; model-card.json with provenance, version and SHA-256. In addition to Ultralytics' selected-F1 P/R, the report includes explicit one-to-one matching counts and class-wise P/R at confidence 0.35 and IoU 0.5 using deployment preprocessing. Undefined metrics are null. Missing classes in the held-out set remain unevaluated. Do not tune thresholds on the test set. Compare operating thresholds on validation data, then report a locked test evaluation. Use a new output folder for every run; existing staged datasets are rejected to avoid stale files. Deterministic seeds improve reproduction but do not guarantee bit-identical GPU results; retain the dependency lock, hardware, CUDA/driver and base-weight hashes with each run.

Evaluate independently supplied weights:

```sh
python -m ml.pipeline evaluate --manifest datasets/roads/manifest.json --output ml/runs/eval-v1 --weights models/model.pt --device cpu --version road-v1
```

For real inference, copy model.pt and model-card.json to `models/`, set `INSTALL_YOLO=true`, `INFERENCE_MODE=yolo`, `DEMO_MODE=false` in `.env`, and rebuild/recreate:

```sh
docker compose up --build -d inference worker api
```

The adapter rejects hash mismatches and class maps that omit model classes. A deployment can support a subset of classes if its model and mapping explicitly match; unsupported classes must not be represented as detectable. Rutting detection is an appearance candidate, not a depth measurement.

## Calibrated severity

The built-in heuristic is `min(100, class_base + min(60, image_area_ratio × 240))`, version `visual-screening-v1`. A segmentation mask fraction is preferred when present; otherwise bounding-box area is a proxy. These fractions are viewpoint-dependent. Confidence does not reduce severity. Base scores are policy choices in `backend/app/scoring.py`, not learned engineering measurements.

Collect expert visual ratings using a documented rubric and multiple raters. The CSV columns are `raw_score,expert_score,route_group,split`. At least 20 training and 10 route-disjoint held-out ratings are enforced as a software guard, not a recommendation that this sample size is sufficient for deployment.

```sh
python -m ml.calibrate datasets/expert-ratings.csv --output models/calibration.json --version visual-cal-v1 --provenance "Approved survey campaign, rubric version and annotation owners" --model-sha256 YOUR_MODEL_SHA256
```

This fits monotonic isotonic knots and reports held-out MAE. The worker rejects artifacts bound to a different model hash. Configure `CALIBRATION_PATH=/models/calibration.json` in the worker environment and mount the artifact read-only. Calibrated output is tied to expert visual scores; it still does not measure metres, depth or PCI. Revalidate after model, camera, preprocessing, class policy or domain changes. Preserve previous model and calibration artifacts for rollback and interpretation of historical records.

## Authoritative references

Implementation uses [Ultralytics training](https://docs.ultralytics.com/modes/train/) and [validation](https://docs.ultralytics.com/modes/val/) interfaces; review [Ultralytics licensing](https://www.ultralytics.com/license) before selecting a distribution arrangement. Geographic distances follow [PostGIS ST_DWithin geography semantics](https://postgis.net/docs/ST_DWithin.html). Password/JWT integration follows the [FastAPI security pattern](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/). These references describe interfaces, not evidence of this application's accuracy.


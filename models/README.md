# Trusted model artifacts

No trained weights or evaluation results are bundled. Demo inference emits a deterministic synthetic fixture regardless of image content. It is useful only for exercising integration.

For real inference, train/evaluate with `python -m ml.pipeline`, copy the output `model.pt` and `model-card.json` here, install the inference ML extra/build argument, and set `INFERENCE_MODE=yolo`, `DEMO_MODE=false`. The service validates SHA-256, dataset provenance and the complete model class mapping before loading weights. Only administrators should provision this directory: PyTorch weight deserialization is a trusted-code boundary.

The pipeline uses pretrained YOLO11n transfer learning as a compact baseline, not as evidence of road-defect performance. It supports detection training; the inference adapter also accepts externally trained Ultralytics segmentation models with matching class mapping. Pixel mask area is an image-relative proxy. Assess class balance, unseen cities, lighting, weather, camera height, blur and route leakage before rollout. A zero-detection frame is not proof of healthy pavement.


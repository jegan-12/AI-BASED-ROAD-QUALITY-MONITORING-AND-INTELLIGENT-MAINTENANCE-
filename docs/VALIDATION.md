# Validation record

Final verification: 17 October 2026. Platform: Windows, Python 3.12 virtual environment, Node 20.20.2 and Chromium. The application uses the exact Python versions in `backend/constraints.txt` and Node versions in `frontend/package-lock.json`.

## Executed checks

| Check | Result | Scope |
|---|---|---|
| Python test suite | 40 passed; 2 skipped | API/RBAC, token revocation, idempotency, validation, review conflicts, merges/audit, CSV escaping, image preprocessing, video decode, GPS interpolation, NMS, temporal association, leases/fencing, failure rollback, synthetic inference, dataset leakage/hash checks, calibration and model binding, fixed-threshold metrics, migrations |
| Live HTTP integration smoke | Passed, exit code 0 | Separate API, inference and worker processes; image and video upload; durable queue; synthetic inference; two video observations retained under one defect; authenticated evidence; review; CSV; real-only filtering; RBAC; owned-process cleanup |
| Browser tests | 8 passed | Mocked synthetic API fixtures: inspection/review, filtering, analytics, download, navigation, login error, widths 320/375/414/768/1440 |
| Frontend production build | Passed | Strict TypeScript check and Vite bundle |
| Python compile check | Passed | Backend, inference, ML and helper scripts |
| Dependency consistency | Passed | `pip check` |
| Python dependency audit | No known vulnerabilities reported | All 43 pinned direct/transitive project dependencies; database query via pip-audit, no package installation during audit |
| Node dependency audit | 0 vulnerabilities reported | Final lockfile, including formatter |
| Migration round trip | Passed | Fresh disposable SQLite upgrade/downgrade/upgrade |
| PostgreSQL migration SQL | Generated successfully | Offline compilation includes generated geography and GiST DDL; not a live database execution |
| OpenAPI | Generated | `docs/openapi.json`; typed primary request and response models |

The test client emits one upstream deprecation warning about its HTTPX compatibility adapter. The tests and real HTTP smoke still pass. Dependency audit results are a point-in-time advisory check, not proof of security or a substitute for review.

## Explicitly not verified here

* **Docker/Compose runtime and Linux images:** Docker is not installed in this environment. Dockerfiles and Compose configuration are supplied; CI includes image builds and Compose configuration validation. No CI run on a remote provider has been claimed.
* **Live PostgreSQL/PostGIS:** the two tests requiring `TEST_POSTGIS_URL` skipped. Their coverage includes generated geography/index existence, metre-based distance queries, duplicate candidate lookup and `SKIP LOCKED` queue behavior. CI provisions a disposable PostGIS database for them.
* **Real road detection, GPU execution and model training:** no approved dataset or road-specific weights were provided. The YOLO adapter and training/evaluation code exist, but real model execution and accuracy have not been measured here. Synthetic fixtures do not validate computer vision performance. Full optional Torch/Ultralytics dependency closure is not installed or GPU-tested; the direct optional Ultralytics pin was advisory-checked.
* **Field-calibrated severity:** calibration code and safeguards passed synthetic unit tests. No expert field-rating artifact was supplied, so the default remains explicitly uncalibrated. No depth, area in square metres, PCI or model accuracy is claimed.
* **External basemap availability:** tile requests failed during browser QA. The dashboard displayed its basemap-unavailable warning; interactive markers and the defect register remained usable. Configure and verify a suitable tile provider before deployment.
* **Production load, HA, disaster recovery, SSO and penetration testing:** not exercised. Required rollout gates are in SECURITY.md.

## Reproduce

```sh
python -m pytest -q
python -m scripts.smoke
python -m scripts.export_openapi
python -m compileall -q backend inference ml scripts
python -m pip check
python -m pip_audit --disable-pip --no-deps -r backend/constraints.txt
cd frontend
npm run build
npm test
npm audit --audit-level=high
```

Install Chromium with `npx playwright install chromium` before browser tests. This host reused an existing Chromium installation through `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; CI installs its own compatible browser. Browser screenshots are synthetic UI fixtures, not real survey results.


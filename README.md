# RoadScope

A production-oriented reference implementation for road defect screening and maintenance review. FastAPI, PostgreSQL/PostGIS, a leased background worker, an isolated YOLO adapter, and a React/TypeScript map dashboard.

**Data honesty:** no road-specific weights or labeled dataset were supplied. The default development profile uses clearly labeled synthetic fixtures. It does not detect actual damage. Real inference requires registered road-specific weights. Severity is an uncalibrated visual screening score until an expert calibration artifact is supplied. Neither mode estimates physical depth or certified pavement condition index (PCI).

## Start with Docker Compose

Prerequisites: Docker Engine/Desktop with Compose v2, Python 3.12 for generating local configuration, approximately 4 GB memory for the demo. The YOLO profile may need substantially more memory/GPU capacity.

```sh
python scripts/init_env.py
docker compose up --build -d
docker compose exec api python -m backend.app.cli create-admin --username admin
docker compose exec api python -m backend.app.cli seed
```

The administrator command prompts for a password; there are no built-in credentials. Open [the dashboard](http://localhost:8080). Use the account you created. The seed command inserts 36 synthetic records around Bengaluru and is idempotent. They are invented examples, not observations of those roads.

Check service state:

```sh
docker compose ps
docker compose logs --tail=100 api worker inference migrate
```

API docs are available inside the API service at `/api/docs`; the same-origin gateway exposes the complete contract at [OpenAPI JSON](http://localhost:8080/api/openapi.json) and [interactive API docs](http://localhost:8080/api/docs). Every business endpoint requires a bearer token. The health endpoint is public.

## Local Python / frontend development

The SQLite profile is for quick development and tests only. It does not provide PostGIS or concurrent-worker locking. Use exactly one worker with SQLite.

```sh
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python scripts/init_env.py
alembic upgrade head
python -m backend.app.cli create-admin --username admin
python -m backend.app.cli seed
```

Run these in separate terminals from the repository root:

```sh
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
uvicorn inference.service:app --host 127.0.0.1 --port 8001
python -m backend.app.worker
```

Frontend, in a fourth terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [the local dashboard](http://127.0.0.1:5173). Vite proxies `/api` to port 8000. Direct API docs: [Swagger UI](http://127.0.0.1:8000/api/docs).

## Validate

```sh
pytest -q
python -m scripts.smoke
python -m compileall -q backend inference ml scripts
python -m scripts.export_openapi
cd frontend
npm run build
npx playwright install chromium
npm test
npm audit --audit-level=high
```

The browser suite uses explicitly mocked API fixtures to isolate dashboard behavior; it is not a substitute for the real-stack smoke test. The PostGIS test skips unless `TEST_POSTGIS_URL` is configured. See [validation evidence](docs/VALIDATION.md) for checks actually executed in the build environment and their limits.

## Repository guide

```text
backend/app/           API, RBAC, models, scoring, GPS, deduplication, worker, CLI
backend/migrations/    Alembic schema + PostGIS geography/index
inference/             Internal authenticated inference service and Dockerfile
frontend/src/          React map, register, inspection, upload, analytics, access UI
frontend/tests/        Playwright interaction and responsive-layout tests
ml/                    Dataset audit, training, evaluation and severity calibration
models/                Administrator-provisioned, trusted model artifacts
tests/                 API, vision, worker, inference and PostGIS tests
scripts/               Secret generation, contract export, integration smoke test
docs/                  Architecture, API contract, model/data guidance, runbook
compose.yaml           Local development services, private network and volumes
.github/workflows/     Python, PostGIS, browser, dependency and image-build checks
```

Read [architecture and implementation phases](docs/ARCHITECTURE.md), [API contract](docs/API.md), [SQL schema](docs/schema.sql), [phase-by-phase runbook](docs/RUNBOOK.md), [model/data workflow](docs/MODELS.md), and [security/deployment guidance](docs/SECURITY.md). Synthetic upload metadata examples are in `examples/`.

## Operating limits

GPS is camera location with reported uncertainty. Bounding boxes/mask fractions are image-relative; they do not give road area or depth. Automatic repeated-frame association is approximate and preserves observations. Cross-survey duplicate candidates need human review. The health indicator covers observed active defects, with unknown network coverage. Real model precision/recall/mAP remain unavailable until evaluation on a suitable held-out dataset. Confidence is a detector output, not a calibrated probability.

The local Compose database uses a development owner account. Separate migration/runtime roles, TLS, backup restoration, approved model/data licensing, a production tile provider, traffic/load testing, and domain-specific evaluation are release gates. This repository is not a certification of operational readiness.


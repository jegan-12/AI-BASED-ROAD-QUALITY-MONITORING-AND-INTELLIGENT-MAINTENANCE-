# Incremental implementation and validation runbook

All commands assume the repository root and an activated Python virtual environment unless noted. Windows PowerShell and POSIX equivalents are listed in README. Expected results below are acceptance criteria, not assertions that every environment has passed them. See VALIDATION.md for the executed evidence.

## Phase 1 — requirements and architecture

Deliverables: ARCHITECTURE.md (diagram, requirements, data model, formulas and limitations), API.md, MODELS.md and SECURITY.md.

Command: `python scripts/init_env.py`.

Expected: `.env` with independent random secrets and `data/media/`. Troubleshooting: if `.env` exists, preserve it; fill missing variables manually rather than overwriting credentials. No secrets are printed. A model/data source is not required for a synthetic demo; it is required for actual road detection.

## Phase 2 — backend and persistence

Deliverables: backend/app/config.py, db.py, models.py, schemas.py, security.py, main.py, cli.py, migrations and backend tests.

```sh
python -m pip install -r backend/requirements.txt
alembic upgrade head
python -m backend.app.cli create-admin --username admin
pytest -q tests/test_api.py
python -m scripts.export_openapi
```

Expected: tables and Alembic revision created, account created without a default password, API tests pass and OpenAPI JSON exported. SQLite has no geography column; PostgreSQL adds the generated geography column and GiST index. Use `docker compose up -d db migrate` for PostgreSQL migration validation.

Troubleshooting: connection refused → check DB health/URL; missing PostGIS extension → provision PostGIS as DB administrator; signing-key error → generate ≥32-character secrets; 401 → login again; 403 → use the required role; 409 → reload stale record or reuse the original idempotent upload content; 429 → wait 15 minutes and inspect login attempts.

## Phase 3 — AI pipeline and worker

Deliverables: vision.py, scoring.py, worker.py, inference/service.py, ml/pipeline.py, ml/calibrate.py and relevant tests.

```sh
pytest -q tests/test_vision.py tests/test_worker.py tests/test_inference.py
uvicorn inference.service:app --host 127.0.0.1 --port 8001
# Separate terminal:
python -m backend.app.worker
```

Expected in demo mode: authenticated /predict returns `synthetic=true`, a fixture box and actual processing latency; metrics remain null. Worker jobs complete with canonical defects and retained observations. Real mode instructions are in MODELS.md.

Troubleshooting: `inference_unavailable` → check service key, DNS/network and model startup logs, then retry failed job; invalid metadata/result → check GPS ordering, coverage, media format, pixel/frame limits and model contract; model hash/class-map error → restore matching trusted artifacts. Generic COCO weights cannot silently act as a road model. Missing trained weights means real detection remains unavailable.

## Phase 4 — frontend

Deliverables: frontend/src files, tokens/styles, Playwright tests, Vite/TypeScript configuration.

```sh
cd frontend
npm ci
npm run build
npx playwright install chromium
npm test
npm run dev
```

Expected: strict typecheck and static build succeed; browser tests exercise filtering, inspection/review, navigation/export, errors and widths 320/375/414/768/1440. The tests use synthetic mocked API data. In development the app connects to the real API through Vite's proxy.

Troubleshooting: blank data → check API health, bearer session and browser network response; 502 → API not running on 8000; basemap fails → check tile-provider access (the register remains usable); no photo for seed → expected, seeds are not real imagery; no model metrics → expected until a registered model has measured evaluation. Text search applies only to loaded records, and CSV uses server filters.

## Phase 5 — integration and deployment

Deliverables: Compose, three Dockerfiles, Nginx gateway, CI workflow, .env.example, scripts and runbooks.

```sh
docker compose up --build -d
docker compose ps
docker compose exec api python -m backend.app.cli create-admin --username admin
docker compose exec api python -m backend.app.cli seed
```

Expected: db, api and inference healthy; migration service exits zero; worker running; dashboard at localhost:8080. Log in, upload a JPEG with metadata, observe completed job, inspect image/box, save a review, filter synthetic records and export CSV. Repeat with a short video and a complete GPS track. Stop/start the worker during an upload and verify lease recovery after two minutes.

Run PostGIS tests against a disposable migrated DB by setting `TEST_POSTGIS_URL` and then `pytest -q -m postgis`. CI provides this database automatically. The test checks the generated geography schema, GiST index and metre-based distance semantics.

Troubleshooting: Docker command absent → install Docker Desktop/Engine or use the documented local SQLite profile; unhealthy DB → inspect volume permissions/password and image architecture support; inference OOM → smaller model/batch, resource sizing or GPU deployment; media permission error → preserve UID 10001 ownership on mounted volumes; frontend build network error → retry registry access; schema mismatch → run migrations before app rollout.

Before release, execute SECURITY.md's operational gates and record a real dataset/model evaluation. The development smoke path alone is not evidence of field accuracy or production load tolerance.


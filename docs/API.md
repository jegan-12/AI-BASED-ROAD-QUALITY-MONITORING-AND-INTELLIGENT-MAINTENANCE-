# API contract v1

The machine-readable authority is `docs/openapi.json`, generated from the implemented FastAPI application. Regenerate with `python -m scripts.export_openapi`. Live schema: `/api/openapi.json`; interactive docs: `/api/docs`.

All times are ISO 8601 with timezone offsets. All coordinates are WGS84 longitude/latitude; upload fields are explicitly named. UUIDs identify records. Errors use `{"detail": "message"}` (422 validation errors can contain a list); unexpected failures include a request ID. `X-Request-ID` accompanies responses. Bearer tokens expire after 30 minutes by default and are checked against current account status/revision on every request.

| Method / path | Permission | Contract |
|---|---|---|
| GET `/api/health` | Public | DB connectivity, demo flag |
| POST `/api/auth/token` | Public, throttled | OAuth2 form username/password → token and user |
| GET `/api/auth/me` | All roles | Current identity |
| POST `/api/auth/logout` | All roles | Revoke all current tokens for this user |
| GET/POST `/api/users` | Admin | List/create accounts |
| PATCH `/api/users/{id}` | Admin | Change role/enabled, revoke tokens; self-change rejected |
| POST `/api/jobs` | Inspector/admin | Multipart `file`, JSON-string `metadata`; `Idempotency-Key` header; 202 |
| GET `/api/jobs` | All | Latest 50 jobs, max 200 via `limit` |
| GET `/api/jobs/{id}` | All | State/progress/attempts/error/model/latency |
| POST `/api/jobs/{id}/retry` | Inspector/admin | Failed jobs only; resets attempts; audited |
| GET `/api/defects` | All | Filtered `{items,total,offset,limit}`, max 2,000/page |
| GET `/api/defects/{id}` | All | Detail and up to 200 original observations |
| PATCH `/api/defects/{id}` | Inspector/admin | `{status,note,critical_location,revision}`; optimistic concurrency, 409 on stale revision |
| POST `/api/defects/{id}/merge` | Inspector/admin | `{target_id,revision,reason}`; same class/source within 50 m; observations retained; audit |
| GET `/api/observations/{id}/image` | All | Authenticated JPEG evidence; 404 when seed has no original image |
| GET `/api/analytics` | All | Counts, class/status/day groups, observed health, top 10 priorities |
| GET `/api/reports/defects.csv` | All | Current filters, ≤50,000 records, spreadsheet formula escaping |
| GET `/api/model` | All | Model card or unavailable state; no invented metrics |
| GET `/api/audit` | Admin | Latest 200 events; optional `entity_id` |

Shared defect/analytics/report filters: `defect_class`, `status`, `synthetic=true|false`, `min_severity=0..100`, `since`, `until`, `bbox=west,south,east,north`. Antimeridian-crossing bounding boxes are rejected; split them into two requests. Text search in the dashboard applies only to loaded records; the UI labels this. Export uses server filters, not this local text search.

Image capture metadata:

```json
{"captured_at":"2026-10-01T10:00:00Z","latitude":12.98,"longitude":77.60,
 "gps_uncertainty_m":8,"road_name":"Survey road"}
```

Video capture metadata:

```json
{"captured_at":"2026-10-01T10:00:00Z","road_name":"Survey road",
 "gps_track":[
   {"offset_seconds":0,"latitude":12.98,"longitude":77.60,"uncertainty_m":5},
   {"offset_seconds":2,"latitude":12.98002,"longitude":77.60,"uncertainty_m":5}
 ]}
```

The track must begin at zero, increase strictly, cover every sampled frame, and have no interpolation gap longer than ten seconds. Interpolation adds half the distance between fixes to uncertainty. Longer videos need longer tracks. Neither API nor worker silently substitutes a stationary point for a video track.

Job states: `queued → processing → completed`; transient inference failure returns to queued up to three attempts; invalid media/result or exhausted attempts goes to `failed`. Lease expiry allows recovery. A fencing token prevents a displaced worker from committing. Review states: new, confirmed, scheduled, repaired, rejected. Merged records remain stored but leave list/report/analytics queries.

Internal service: `/predict` accepts a JPEG in multipart `file`, authenticated with `X-API-Key`. Response validates normalized xyxy boxes, taxonomy, confidence, latency, model SHA/version, synthetic flag and provenance. `/model` requires the same key. `/health` is internal-network public.


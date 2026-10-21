# Security and deployment notes

## Implemented controls

Argon2 password hashes; expiring signed JWTs with issuer/audience/revision checks; current role and enabled status read from DB on each request; logout and account changes revoke tokens; database-backed login throttling; explicit CORS; private authenticated media; randomized upload filenames; decode/pixel/byte/frame/duration limits; SQLAlchemy bound queries; CSV formula escaping; optimistic review revisions and row locks; audit records for changes; internal inference key; no user-uploaded model weights; CSP/nosniff/frame headers; non-root application containers; private DB/inference network; localhost-only gateway binding; log rotation; no committed secrets.

JWTs live in browser sessionStorage and are removed on logout. XSS can compromise browser-held tokens; CSP, dependency patching and the absence of raw HTML insertion reduce this risk. Prefer an organization OIDC integration and secure-cookie/BFF architecture for a public rollout. The MVP account lifecycle supports creation, role/enable changes and revocation; password reset/MFA/SSO require deployment-specific integration.

## Before public deployment

* Use TLS at the ingress, strict trusted-proxy configuration and per-identity/client rate limits. The development login limiter keys the gateway IP and username; add an ingress-wide abuse policy for production and configure client identity forwarding explicitly.
* Split DB extension/schema ownership and runtime DML roles; the local PostGIS image initializes a development owner. Do not use the Compose owner credential as a public-production runtime role.
* Move uploads to private encrypted object storage with checksum verification, malware screening, lifecycle/retention and restore procedures. Do not expose the media directory as static content. Review imagery/GPS retention and face/plate redaction requirements.
* Use a secret manager, TLS between services where required, least-privilege network policies, image digests, SBOMs and regular vulnerability scans. Both Python and Node dependencies require ongoing patching.
* Store immutable audit events externally if tamper evidence is a requirement. Current application auditing is transactional, but a DB administrator can alter rows.
* Add organizational OIDC/MFA, password recovery and centralized account provisioning. This is a single-organization application; do not reuse it for multiple tenants without tenant isolation throughout storage and APIs.
* Provision a licensed/approved basemap service. OpenStreetMap's public tile endpoint is a development default; follow its usage policy and do not prefetch tiles for bulk use. Tile requests reveal the viewed region to the provider.
* Validate expected volumes, concurrency and recovery on PostgreSQL. Track queue depth, oldest queued age, lease expiry count, failed jobs, inference p95, HTTP error rate, disk capacity and DB backup age. Worker logs are structured event JSON; exception stack traces remain multiline diagnostic output.
* Test restore, deploy rollback and model rollback. Human review and a representative held-out evaluation are mandatory organizational gates before autonomous maintenance decisions.

## Backup and restore rehearsal

For a disposable development environment:

```sh
docker compose exec -T db pg_dump -U roadscope -d roadscope -Fc -f /tmp/roadscope.dump
docker compose cp db:/tmp/roadscope.dump ./roadscope.dump
```

Back up the private media volume and model/calibration artifacts on the same retention schedule, with an inventory of checksums. Restore the dump to a new isolated database using `pg_restore`, verify schema revision and row counts, then verify authenticated image retrieval and replay a synthetic job. Do not restore over a live database. Production should use managed point-in-time recovery and scheduled restore drills.

## Failure handling

Failures return stable public codes; details stay in server logs. Invalid videos fail the entire job with no partial defect writes. Inference network/5xx errors retry at most three times. Expired leases are reclaimed, and fenced workers cannot commit. The next loop waits two seconds when idle and five seconds after DB-loop errors. There is no dead-letter broker; failed job rows form the inspection/retry queue.


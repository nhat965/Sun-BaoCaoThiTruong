# V3 hardening notes

## Controls implemented

- State-changing import routes fail closed when `ADMIN_API_TOKEN` is absent.
- `Authorization: Bearer ...` is compared using constant-time comparison. Reader tokens receive `403`; missing/invalid tokens receive `401` with `WWW-Authenticate`.
- Admin imports are rate-limited per actor and client address. The limit is configured by `ADMIN_RATE_LIMIT_PER_MINUTE`.
- Every import authorization outcome and successful import writes an `audit_logs` record. Tokens are never written to the record.
- Provider circuit state is shared across request-created service/manager objects and transitions closed → open → half-open → closed. Source health is persisted without masking connector errors.
- CSV bodies have explicit size limits and required-column validation. Financial rows use an allowlisted period/statement vocabulary and numeric/date parsing.
- External financial/news content remains untrusted input; only normalized values and metadata are persisted.

## Deployment requirements

Set a high-entropy `ADMIN_API_TOKEN` out-of-band, keep it server-side, put the service behind TLS and an edge rate limiter, and run Alembic migrations before serving traffic. Do not expose `/securities/import` or `/financials/import` through a public reverse proxy without the Bearer dependency.

The repository does not implement user accounts or token rotation yet. `READER_API_TOKEN` is a simple transitional role boundary, not a replacement for an identity provider. Production should add short-lived credentials, rotation and centralized authorization before multi-user deployment.

## Remaining review items

- Dependency vulnerability remediation requires a reachable npm advisory service and a deliberate lockfile update.
- Production host validation, TLS termination, centralized rate limiting, secret rotation and penetration testing must be verified in deployment infrastructure.
- The frontend has no privileged write controls because admin imports are API-only; no admin token is exposed through `NEXT_PUBLIC_*` variables.

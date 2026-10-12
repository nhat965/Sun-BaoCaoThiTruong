# V4.1 progress

Statuses are evidence-based. External feeds are not marked complete without an authorized successful request.

## Milestone 1 — P0 correctness and security

Status: **COMPLETE locally**

### Implemented

- Replaced prose-wide numeric matching with typed financial claims and deterministic verification of evidence ID, symbol, metric identity, value, compatible unit, period and forecast support.
- User-facing analyst text is rendered only from accepted claim fields. Invalid provider JSON and rejected claims fall back to a verified latest-price claim.
- Added `claim_token`, `run_id`, `claimed_at`, `lease_expires_at`, `worker_id` and `heartbeat_at` to jobs and execution history in migration `0009`.
- Only the current unexpired owner can heartbeat or finish a run. Reclamation expires the old run, and an old worker cannot modify the new owner or its output.
- Replaced the `Content-Length`-only check with bounded ASGI body buffering that counts actual streamed bytes. Documented the matching reverse-proxy limit.
- Preserved admin/reader authorization, audit metadata, production secret validation and dedicated AI rate limiting.

### Modified endpoints

- `POST /api/v1/analyst/chat`: provider output now uses a strict structured-claim contract and verified narrative.
- `POST /api/v1/jobs/{job_id}/run`: execution now uses tokenized lease ownership.
- All HTTP endpoints: actual request body is bounded by `MAX_REQUEST_BYTES`.

### Verification

- Ruff: PASS.
- Pytest: PASS — 35 tests after the complete claim suite (32 before the final three claim cases).
- Alembic: clean `base → 0009`, `0009 → base`, and `base → 0009` on a temporary SQLite database.
- PostgreSQL: BLOCKED on this host because Docker and `psql` are unavailable.

### Risks and limits

- The built-in fixed-window rate limiter is process-local; a shared production store is still required for multiple API processes.
- Lease ownership is database-enforced, but a production worker must call `heartbeat()` during work longer than the configured lease.
- The body limiter buffers at most the configured request size in memory; the reverse proxy should enforce an equal or smaller limit.

### Next

Milestone 2 extends registry synchronization, provider/data-quality detail and corporate-action provenance without claiming licensed live coverage.

## Milestones 2–8

## Milestone 2 — Vietnamese market-data foundation

Status: **PARTIAL** — all feasible local workflows are implemented; licensed full-market data remains blocked.

### Implemented

- Added authorized XLSX securities-master import alongside CSV, including incremental upsert, duplicate rejection, inactive/delisted statuses, provider ID maps and Vietnamese search compatibility.
- Added authorized corporate-action CSV storage and retrieval for splits, cash dividends, bonus shares and rights issues. No action is inferred and no price is silently adjusted.
- Migration `0010` persists zero-volume, over-20% jump and over-four-day calendar-gap flags on each price observation.
- `/api/v1/data-quality` now reports active symbols by exchange, symbols with/missing price history, coverage percentage, latest timestamps by exchange and aggregate quality alerts.
- The existing data-quality dashboard now exposes these coverage and alert details responsively.

### Modified/created endpoints

- `POST /api/v1/securities/import/xlsx`
- `POST /api/v1/stocks/{symbol}/corporate-actions/import`
- `GET /api/v1/stocks/{symbol}/corporate-actions`
- `GET /api/v1/data-quality`

### Verification

- Backend Ruff: PASS.
- Backend Pytest: PASS — 39 tests.
- Frontend lint/build: PASS.
- Alembic clean upgrade/downgrade/re-upgrade through `0010`: PASS on SQLite.

### Real integrations and blockers

- FireAnt's official API documentation advertises OAuth scopes including `companies-read`, `finance-read` and `posts-read`; no access token, proven scopes, entitlement or redistribution agreement was supplied, so data calls remain blocked.
- HNX publishes official listing pages, but this project does not scrape them without confirmed automated-use and redistribution permission. Operators can load an authorized export via CSV/XLSX.
- Yahoo remains a delayed development source, not a licensed production feed. Docker/PostgreSQL verification remains blocked on this host.

## Milestones 3–8

## Milestone 3 — Financial statements and valuation

Status: **PARTIAL**

- Quarterly growth now compares the same fiscal quarter in the prior year; annual/TTM records use the like-for-like prior fiscal year. Missing comparison periods remain null and are disclosed.
- Added `POST /api/v1/fundamentals/valuation/dcf/sensitivity` for explicit user-supplied discount/growth grids. Invalid growth/discount pairs return null, not an invented value.
- Ruff and 41 backend tests pass. No migration was required.
- Historical valuation bands, peer and sector comparison remain blocked until verified historical multiples and classifications are supplied.

## Milestones 4–8

Status: **IN PROGRESS**. See `docs/IMPLEMENTATION_STATUS.md` for the truthful capability matrix and external blockers.

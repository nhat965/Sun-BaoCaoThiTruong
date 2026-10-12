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

Status: **IN PROGRESS**. See `docs/IMPLEMENTATION_STATUS.md` for the truthful capability matrix and external blockers.

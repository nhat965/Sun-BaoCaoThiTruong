# V4 progress

## M1 — Security and reliability

Status: **COMPLETE** for the locally feasible acceptance criteria.

- Public valuation remains a calculation-only route; persistence is admin-only at `/api/v1/fundamentals/valuation/persist`.
- EOD jobs use a database compare-and-set claim, attempt limits, `RETRY_PENDING`, stale-running recovery and one `JobRunRecord` per claim.
- LLM requests have bounded question size, a dedicated per-IP rate limit, timeout configuration and secret-free audit metadata.
- Production settings fail closed when the admin token is missing/weak or hosts contain `*`.
- Global request size limit is enforced in middleware; existing CSV limits remain stricter where applicable.
- Concurrency, auth, production-config and invalid-input regression tests pass (21 backend tests).

Remaining production gap: process-local rate limits need Redis or another shared backend when multiple API workers are deployed.

## Next milestones

- M2: **PARTIAL** — provider capability/quality API and dashboard are implemented with persisted success/failure timestamps, coverage counts, freshness and explicit fixture/configured/unavailable states. Clean migration `0007` and browser QA passed. Authorized full-market securities synchronization and a licensed market feed remain.
- M3: **PARTIAL** — statement scope/amendment metadata, multi-period financial trends and explicit-assumption DCF are implemented in migration `0008`, API and dashboard. Licensed peer/sector/history inputs remain.
- M4: **PARTIAL** — stored news supports bounded source, event-category and publication-time filters; UI filters operate on retrieved metadata. A second verified authorized live feed remains unavailable.
- M5: **PARTIAL** — evidence IDs plus numeric/citation verification reject unsupported LLM output and fall back to deterministic analysis. Production provider evaluation remains credential-dependent.
- M4–M8: only where authorized data or infrastructure is available; otherwise retain explicit BLOCKED/PARTIAL status.

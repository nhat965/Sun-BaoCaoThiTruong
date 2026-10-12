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

- M2: provider capability/quality dashboard and authorized securities synchronization.
- M3: financial trend dashboard, statement scope metadata and transparent valuation history/peer inputs.
- M4–M8: only where authorized data or infrastructure is available; otherwise retain explicit BLOCKED/PARTIAL status.

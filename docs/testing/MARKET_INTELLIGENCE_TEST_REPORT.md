# Market Intelligence test report — PR-A

## Scope

This report covers the Market Data Foundation only: session semantics, canonical provider
selection, market-universe coverage, index provenance and idempotent authorized import.
Breadth, sector, risk, scenarios and frontend intelligence are intentionally deferred to
later PRs.

## Automated coverage

- `tests/test_market_foundation.py` adds independent tests for Vietnam timezone/session
  handling, history-depth denominators, index import provenance and replay idempotency.
- Ruff passes for the backend source and tests.
- Frontend lint and production build pass on the unchanged frontend surface.
- Pytest and Alembic execution are currently blocked on this host because the checked-in
  `.venv` points to `C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe`,
  which is no longer installed. The existing Codex API process was still verified through
  HTTP after the additive schema was reconciled locally.

## HTTP smoke evidence

- `GET /api/v1/health` → 200.
- `GET /api/v1/market/indices` → 200 with `data_status=unavailable` and an explicit
  no-authorized-index limitation.
- `GET /api/v1/data-quality` → 200 with 13 active securities, exchange coverage, history
  depth, zero market-cap/foreign-flow coverage and index coverage `0/4`.

No real-market validation is marked PASS. Yahoo Finance remains a delayed development
source; index, official calendar, market-cap and foreign-flow providers remain BLOCKED until
authorized data is supplied.

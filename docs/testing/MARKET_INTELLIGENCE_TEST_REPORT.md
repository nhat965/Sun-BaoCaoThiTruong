# Market Intelligence test report — production-readiness audit

## Scope

This report records the current `main` audit: session semantics, canonical provider
selection, market-universe coverage, index provenance, breadth, sector, liquidity, risk,
scenario and frontend evidence. The detailed production-readiness table is in
`docs/testing/PRODUCTION_READINESS_AUDIT.md`.

## Automated coverage

- `tests/test_market_foundation.py` adds independent tests for Vietnam timezone/session
  handling, history-depth denominators, index import provenance and replay idempotency.
- Ruff passes for the backend source and tests.
- Frontend lint and production build pass on the unchanged frontend surface.
- Local pytest passed: 119 backend tests.
- Local Ruff passed for `app`, `tests` and `scripts`.
- A temporary SQLite migration cycle (upgrade/downgrade/upgrade) passed at revision `0021`.
- The labelled benchmark passed for 1,000 securities × 200 sessions (200,000 observations);
  it took 207.85 ms on this host and performed zero database writes.
- `pip-audit` is not installed in this environment. A previous local npm production audit
  reported zero vulnerabilities; the latest advisory-endpoint request was unavailable.
- PostgreSQL migration CI remains configured; no local PostgreSQL service is available on
  this host for a direct execution.

## HTTP smoke evidence

- `GET /api/v1/health` → 200.
- `GET /api/v1/market/indices` → 200 with `data_status=unavailable` and an explicit
  no-authorized-index limitation.
- `GET /api/v1/data-quality` → 200 with 13 active securities, exchange coverage, history
  depth, zero market-cap/foreign-flow coverage and index coverage `0/4`.

No real-market validation is marked PASS. Yahoo Finance remains a delayed development
source; index, official calendar, market-cap and foreign-flow providers remain BLOCKED until
authorized data is supplied.

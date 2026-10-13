# Test report — V4.1 Task 02

Date: 2026-10-14 (Asia/Bangkok)

## Automated checks

| Check | Result |
|---|---|
| Backend `ruff check .` | PASS |
| Backend `pytest -q` | PASS — 98 tests |
| Frontend `npm run lint` | PASS |
| Frontend `npm run build` | PASS — Next.js production build |
| Clean Alembic upgrade/downgrade/re-upgrade to `0020` | PASS — temporary SQLite database |
| CI PostgreSQL migration gate | CONFIGURED — PostgreSQL 16 service, full upgrade/downgrade/re-upgrade |
| Dependency audit | PASS — `pip-audit` no known vulnerabilities; production `npm audit` 0 vulnerabilities |
| Market analytics benchmark | PASS — labelled fixture, 1,000 symbols × 200 sessions, 197.65 ms, no writes |
| Responsive browser smoke (desktop + 390×844) | PASS — no horizontal overflow or console errors |
| Impeccable UI detector | PASS — one side-border warning found and removed in the changed frontend targets |
| Legacy database adoption | PASS — schema verified and stamped without deleting data |

Backend coverage additionally exercises authorized XLSX registry ingestion, in-file duplicate rejection, provider IDs, corporate-action imports, idempotent price-quality flags and expanded exchange/history coverage diagnostics. Analyst and automation production integrations remain credential/infrastructure dependent. One upstream Starlette warning recommends migrating from the deprecated TestClient/httpx integration when compatible versions are available.

Task 02 regressions additionally verify explicit provider capability gates, initial versus
incremental price sync, persisted run/error counts, financial unit conversion, retention
of raw value/unit, refusal to overwrite verified BCTC with unverified input, normalized
statement reads and a persisted `BLOCKED` result when automatic BCTC access is unavailable.

Task 01 browser QA verified the default 13-row registry without a query, unaccented
`Hoa Phat` search returning HPG, HOSE and sector filters, symbol sorting, five-row
server pagination, HPG analysis navigation, local watchlist persistence, explicit missing
values for ACV, and layouts at 1440px and 390×844 without page-level horizontal overflow.
The browser console contained no warnings or errors.

Financial regressions verify same-quarter prior-year growth selection and DCF sensitivity cells, including explicit nulls when terminal growth is not below the discount rate. Market analytics regressions also verify complete RVOL20 baselines, timestamp-based freshness, requested-session index alignment and replay idempotency.

Additional regressions verify the closed typed AI tool registry, market breadth/report
snapshot idempotence, leased EOD ownership, exponential retry scheduling, portfolio
average-cost accounting, oversell rejection, CSV idempotency and deterministic social
classification with uncertainty labels.

## Live smoke test

HPG and FPT were requested through the live Yahoo connector on 2026-10-13 using
`scripts/verify_live_pipeline.py`. The first pipeline sync inserted 120 daily rows for each
symbol. The immediate incremental sync inserted zero rows; counts remained 120 → 120 for
both symbols. HPG used provider symbol `HPG.VN`, FPT used `FPT.VN`; the stored latest market
timestamp was `2026-10-09T02:00:00+00:00`, with retrieval timestamps and exact source URLs
persisted in `data_sync_runs`. Normalization marked both series `valid`.

Browser QA against that database showed HPG/FPT live prices in Securities Explorer,
HPG analysis with live provenance, an explicit automatic-BCTC `BLOCKED` badge, zero BCTC
coverage rather than invented values, persisted sync-error diagnostics and no browser
console warnings/errors. At 390×844, `innerWidth=390`, document `scrollWidth=375`, so the
page had no horizontal overflow.

This proves connectivity at that moment only. It does not establish market-data licensing, completeness, exchange-grade accuracy or future upstream availability.

## Not verified here

- FireAnt market data: no access token/scopes/entitlements supplied.
- Live financial statements: no provider credential or redistribution agreement supplied; the tested path is authorized CSV only.
- VPS portfolio data: no supported official integration supplied.
- Docker Compose: Docker engine unavailable.
- Production load, penetration testing, accessibility screen-reader audit and cross-browser matrix.
- GitHub Actions and Docker Compose runtime were not executed locally because Docker/network infrastructure is unavailable here. The workflow now enforces PostgreSQL migrations and dependency audits on every pull request and push to `main`.

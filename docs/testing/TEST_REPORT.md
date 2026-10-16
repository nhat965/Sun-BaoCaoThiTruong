# Test report — V4.1 PR-F release acceptance

Date: 2026-10-15 (Asia/Bangkok)

## Automated checks

| Check | Result |
|---|---|
| Backend `ruff check .` | PASS |
| Backend `pytest -q` | PASS — 119 tests |
| Frontend `npm run lint` | PASS |
| Frontend `npm run build` | PASS — Next.js production build |
| Clean Alembic upgrade/downgrade/re-upgrade to `0021` | PASS — temporary SQLite database |
| CI PostgreSQL migration gate | CONFIGURED — PostgreSQL 16 service, full upgrade/downgrade/re-upgrade |
| Dependency audit | PARTIAL — a previous production `npm audit --omit=dev --audit-level=high` returned 0 vulnerabilities; the latest rerun could not reach the npm advisory endpoint, and `pip-audit` is not installed in this environment |
| Market analytics benchmark | PASS — labelled in-process fixture, 1,000 symbols × 200 sessions, 207.85 ms, no writes; PostgreSQL benchmark added to CI |
| Responsive browser smoke (desktop + 390×844) | PASS — no horizontal overflow or console errors |
| Impeccable UI detector | PASS — one side-border warning found and removed in the changed frontend targets |
| Legacy database adoption | PASS — schema verified and stamped without deleting data |
| PR-F fixture release acceptance | PASS — registry, fixture sync/replay, coverage and admin auth |
| Task 05 capability/reconciliation acceptance | PASS — capability status matrix, explicit external-baseline blocker, API and CLI report |
| PostgreSQL lease acceptance | CI gate — two concurrent claimers must yield exactly one owner |
| Docker Compose graph | CI gate — `docker compose config --quiet`; runtime remains target-host dependent |

Backend coverage additionally exercises authorized XLSX registry ingestion as a standalone importer (including schema initialization), in-file duplicate rejection, provider IDs, corporate-action imports, idempotent price-quality flags and expanded exchange/history coverage diagnostics. Analyst and automation production integrations remain credential/infrastructure dependent. One upstream Starlette warning recommends migrating from the deprecated TestClient/httpx integration when compatible versions are available.

The latest CI PostgreSQL fixture benchmark (1,000 × 200, 3 runs) measured P50/P95
of 732.134/733.884 ms for canonical selection, 254.619/256.252 ms for breadth,
258.411/259.774 ms for sectors, 271.031/271.146 ms for liquidity, and
0.045/0.045 ms for response serialization. Each database operation used one
query; the temporary schema was dropped after the run. RSS was not available
because `psutil` is optional.

Task 02 regressions additionally verify explicit provider capability gates, initial versus
incremental price sync, persisted run/error counts, financial unit conversion, retention
of raw value/unit, refusal to overwrite verified BCTC with unverified input, normalized
statement reads and a persisted `BLOCKED` result when automatic BCTC access is unavailable.

Task 05 adds a read-only capability matrix and reconciliation report. The current local
database contains the 13-row bootstrap securities file; no SSI/FiinGroup credential or
redistribution entitlement was supplied, so live full-market acquisition remains
`BLOCKED_EXTERNAL_DEPENDENCY`. Fixture/import paths are reported separately and are not
promoted to live verification.

The official SSI SDK boundary is covered by mocked DailyOhlc, securities-master and
DailyIndex response tests. No real SSI request was made in this environment because
credentials, account approval and redistribution rights were not supplied.

Task 01 browser QA verified the default 13-row registry without a query, unaccented
`Hoa Phat` search returning HPG, HOSE and sector filters, symbol sorting, five-row
server pagination, HPG analysis navigation, local watchlist persistence, explicit missing
values for ACV, and layouts at 1440px and 390×844 without page-level horizontal overflow.
The browser console contained no warnings or errors.

Financial regressions verify same-quarter prior-year growth selection and DCF sensitivity cells, including explicit nulls when terminal growth is not below the discount rate. Market analytics regressions also verify complete RVOL20 baselines, delayed/fixture/unconfirmed freshness, weekend and suspicious-gap session alignment, conflicting provider duplicates and replay idempotency.

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
- Docker Compose runtime: Docker engine unavailable on this workstation; CI validates the Compose graph, target-host smoke remains required.
- Local PostgreSQL benchmark: blocked because no service was listening on `localhost:5432`; the CI PostgreSQL service runs the isolated benchmark.
- Production load, penetration testing, accessibility screen-reader audit and cross-browser matrix.
- GitHub Actions and Docker Compose runtime were not executed locally because Docker/network infrastructure is unavailable here. The workflow now enforces PostgreSQL migrations and dependency audits on every pull request and push to `main`.

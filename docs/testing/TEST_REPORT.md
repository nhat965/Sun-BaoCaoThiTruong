# Test report — V4

Date: 2026-10-12 (Asia/Bangkok)

## Automated checks

| Check | Result |
|---|---|
| Backend `ruff check .` | PASS |
| Backend `pytest -q` | PASS — 41 tests |
| Frontend `npm run lint` | PASS |
| Frontend `npm run build` | PASS — Next.js production build |
| Clean Alembic upgrade/downgrade/re-upgrade to `0010` | PASS — temporary SQLite database |
| Responsive browser smoke (desktop + 390×844) | PASS — no horizontal overflow or console errors |
| Impeccable UI detector | PASS — no findings in changed frontend targets |
| Legacy database adoption | PASS — schema verified and stamped without deleting data |

Backend coverage additionally exercises authorized XLSX registry ingestion, in-file duplicate rejection, provider IDs, corporate-action imports, idempotent price-quality flags and expanded exchange/history coverage diagnostics. Analyst and automation production integrations remain credential/infrastructure dependent. One upstream Starlette warning recommends migrating from the deprecated TestClient/httpx integration when compatible versions are available.

Financial regressions verify same-quarter prior-year growth selection and DCF sensitivity cells, including explicit nulls when terminal growth is not below the discount rate.

## Live smoke test

HPG was requested through the live connector on 2026-10-12. Yahoo returned 260 daily bars; normalization marked them `valid`, incremental storage contained 260 unique observations, and `technical-v2` completed. The RSS request completed with zero currently matching headlines, which is a valid empty result rather than fabricated coverage.

This proves connectivity at that moment only. It does not establish market-data licensing, completeness, exchange-grade accuracy or future upstream availability.

## Not verified here

- FireAnt market data: no access token/scopes/entitlements supplied.
- Live financial statements: no provider credential or redistribution agreement supplied; the tested path is authorized CSV only.
- VPS portfolio data: no supported official integration supplied.
- Docker Compose: Docker engine unavailable.
- Production load, penetration testing, accessibility screen-reader audit and cross-browser matrix.
- `npm audit` could not reach the registry endpoint in this environment; dependency remediation remains a release gate.

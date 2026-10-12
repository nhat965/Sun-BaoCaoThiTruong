# Test report — V2

Date: 2026-10-12 (Asia/Bangkok)

## Automated checks

| Check | Result |
|---|---|
| Backend `ruff check .` | PASS |
| Backend `pytest -q` | PASS — 14 tests |
| Frontend `npm run lint` | PASS |
| Frontend `npm run build` | PASS — Next.js production build |
| Clean Alembic upgrade to `0002` | PASS |
| Legacy database adoption | PASS — schema verified and stamped without deleting data |

Backend coverage exercises API happy/error paths, normalization rejection and deduplication, unaccented registry search, deterministic financial formulas, news relevance/deduplication, technical edge cases and PDF creation. One upstream Starlette warning recommends migrating from the deprecated TestClient/httpx integration when compatible versions are available.

## Live smoke test

HPG was requested through the live connector on 2026-10-12. Yahoo returned 260 daily bars; normalization marked them `valid`, incremental storage contained 260 unique observations, and `technical-v2` completed. The RSS request completed with zero currently matching headlines, which is a valid empty result rather than fabricated coverage.

This proves connectivity at that moment only. It does not establish market-data licensing, completeness, exchange-grade accuracy or future upstream availability.

## Not verified here

- FireAnt market data: no access token/scopes/entitlements supplied.
- VPS portfolio data: no supported official integration supplied.
- Docker Compose: Docker engine unavailable.
- Production load, penetration testing, accessibility screen-reader audit and cross-browser matrix.

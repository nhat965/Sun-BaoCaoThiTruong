# HOSE securities universe acceptance — 2026-10-16

This acceptance covers the HOSE securities-master import only. It does not
claim a full-market OHLCV backfill, canonical financial-statement ingestion,
or real-time entitlement.

## Database boundary

The backend was started from `apps/api`, so the relative SQLite URL
`sqlite:///./market_intelligence.db` resolves to
`apps/api/market_intelligence.db`. The repository-root database is a separate
snapshot and was not merged or modified.

| Database | Securities before | HOSE before | Securities after | HOSE after |
|---|---:|---:|---:|---:|
| `apps/api/market_intelligence.db` (backend) | 13 | 8 | 411 | 406 |
| repository-root `market_intelligence.db` (untouched) | 1,520 | 406 | 1,520 | 406 |

A backup was created before import at
`.runtime/backups/market_intelligence.before-hose-20261016-104746.db`.

## Source reconciliation

The running vnstock v5 gateway returned successful, live read-only responses
for both providers. The source rows were not treated as fixtures.

| Vnstock call | VCI | KBS |
|---|---:|---:|
| `equity.list_by_exchange(source=...)`, HOSE rows | 406 | 406 |
| `equity.list_by_group("HOSE", source=...)` | 430 | 406 |
| Exchange-set overlap | 406 shared symbols | 406 shared symbols |

The 24 VCI group-only symbols are fund/ETF-like instruments and are not in the
stock rows returned by `list_by_exchange`; they were excluded from this stock
universe rather than silently coerced into equities. Absence from one provider
is not treated as delisting.

## Import and replay

The explicit operator import used VCI-preferred metadata with KBS fallback,
stored `source_name=vnstock-vci`, provider IDs, ICB code when available, and
retrieval metadata. The importer preserves existing sector/name/provider
metadata when the incoming source is less complete.

| Result | First run | Replay |
|---|---:|---:|
| Source symbols | 406 | 406 |
| Inserted rows | 398 | 0 |
| Updated rows | 8 | 406 |
| Duplicate symbols created | 0 | 0 |

The replay updates provenance timestamps but does not create another security
row. The API `GET /api/v1/securities?exchange=HOSE` reports `total=406`.
The protected `POST /api/v1/sync/securities/hose` endpoint is available for an
admin-authenticated deployment; local acceptance used the explicit gateway
script because the local admin token was not configured.

## Coverage after import

| Measure | Backend result | Status |
|---|---:|---|
| Active HOSE securities | 406 | REAL VERIFIED |
| HOSE symbols with OHLCV | 5 | REAL VERIFIED, pre-existing rows |
| HOSE OHLCV records | 1,309 | REAL VERIFIED, no new backfill in this task |
| HOSE symbols with canonical BCTC periods | 0 | BLOCKED |

No OHLCV batch was launched for all HOSE symbols. The next safe step is a
5-symbol pilot, then 20–50 symbol batches with checkpoint/resume and quota
monitoring. HNX and UPCoM were not changed by this task.

## Reproduction and evidence

```powershell
cd apps/api
..\\..\\.tools\\python\\python.exe scripts/hose_reconciliation_report.py `
  --api-base http://127.0.0.1:8000 `
  --output ..\\..\\.runtime\\hose_reconciliation.json
..\\..\\.tools\\python\\python.exe scripts/hose_import_from_gateway.py `
  --api-base http://127.0.0.1:8000 `
  --output ..\\..\\.runtime\\hose_import_report.json --confirm
..\\..\\.tools\\python\\python.exe scripts/hose_acceptance_report.py `
  --output ..\\..\\.runtime\\hose_acceptance_report.json
```

Validation completed in this environment:

- `pytest apps/api/tests -q`: 131 passed, 1 warning.
- `ruff check apps/api/app apps/api/tests apps/api/scripts`: passed.
- `npm run lint` in `apps/web`: passed.
- `npm run build` in `apps/web`: passed.
- `git diff --check`: passed (line-ending warnings only).

PostgreSQL migrations and production database acceptance were not claimed in
this SQLite-backed run. Canonical financial statements remain blocked until
schema/unit/period mapping and storage entitlement are verified. No secrets
were added or committed.

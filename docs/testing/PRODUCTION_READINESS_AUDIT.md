# Production-readiness audit

Audit target: `main` at `d2b428d`, hardened on branch
`audit/market-data-production-readiness` in PR #17.

## Task 02 PR reconciliation

PR #5 to #10 were compared with `main` using `git rev-list main..origin/<branch>`
and a three-dot diff. Every branch had zero commits ahead of `main` and an empty
diff. Their code is already in the main history through the Task 03 merge chain.
The six redundant PRs were closed with an explanation; they were not merged a
second time. A closed PR with `mergedAt=null` is expected in this situation.

## Coverage observed from the running API

| Module | Current evidence | Status | Limitation |
|---|---:|---|---|
| Securities registry | 13 active symbols: HOSE 7, HNX 3, UPCoM 3 | PARTIAL | Bootstrap registry, not full-market universe |
| OHLCV | 1,302 persisted observations; 5/13 symbols have history | PARTIAL | Yahoo chart is a development connector and delayed |
| VN-Index / VN30 / HNX-Index / UPCoM-Index | 0/4 stored | BLOCKED | No authorized index feed configured |
| Market cap | 0 symbols | BLOCKED | No provider field available in the active source |
| Actual trading value | 0 current observations | BLOCKED | Volume is not substituted for value |
| Foreign flow | 0 symbols | BLOCKED | No entitled source |
| Financial statements | 0/13 symbols | BLOCKED | Authorized CSV import exists; automatic provider is not entitled |

The `/api/v1/data-quality` endpoint is the coverage dashboard/API. It exposes
counts by market session and exchange, price/value/market-cap coverage, observed
providers, history depth, missing symbols, source health, quality alerts, latest
market/retrieval timestamps, freshness evidence and index coverage. Freshness is
reported as `fresh`, `stale`, `delayed`, `historical`, `fixture`, `unconfirmed` or
`unknown`; without an official exchange calendar a recent weekday is only a
`weekday_candidate`, not proof of realtime data. Fixture data is only enabled by
`MARKET_DATA_MODE=fixture` and is labelled as synthetic.

## Reproduced issues and fixes

| Area | Reproduced issue | Fix |
|---|---|---|
| RVOL20 | A two-to-twenty-observation history produced an RVOL using an incomplete baseline | Require the current observation plus 20 baseline sessions; return `null` otherwise |
| Freshness | Any non-empty current-session map was reported as `fresh`, including old timestamps | Use provenance, session date, official-calendar evidence when available, and a conservative `unconfirmed` fallback; age is only a stale signal |
| Session alignment | Index return used the two latest rows even when the newest index row did not match the requested stock session | Require the target session and an evidenced prior session; reject suspicious weekday gaps, weekend gaps without alignment, and conflicting provider duplicates |
| Idempotency | Replay behavior needed explicit regression coverage | Added replay coverage for risk and scenario snapshots; existing upsert constraints remain in place |

No market values were fabricated while fixing these issues.

## Data-source classification

- **Real request observed:** Yahoo Finance chart historical OHLCV request, marked
  development-only and without a commercial redistribution claim.
- **Authorized-file path:** securities metadata, corporate actions and financial
  statements can be imported only with operator-supplied provenance and rights.
- **Fixture:** deterministic connector used by tests; never selected implicitly
  in production.
- **Configured but blocked:** FireAnt, SSI FastConnect and FiinGroup require
  credentials, entitlement and applicable licensing; VPS SmartOne has no verified
  official read-only API in this repository.

## Benchmark

Run from `apps/api`:

```text
python scripts/benchmark_market_analytics.py
python scripts/benchmark_market_analytics_postgres.py --database-url "$BENCHMARK_DATABASE_URL"
```

The benchmark uses a labelled synthetic fixture with 1,000 securities and 200
sessions per security, performs RVOL/return/MA calculations and writes nothing to
the database. The latest run processed 200,000 observations in 197.82 ms. Its
output is evidence of local computational cost only, not market coverage or data
quality.

The PostgreSQL benchmark creates a temporary schema, loads the same 1,000 × 200
labelled fixture, measures canonical query, breadth, sector, liquidity and API
response serialization P50/P95, query count and optional RSS memory, then drops
the schema. It refuses SQLite and never uses application tables. It was not run
locally because no PostgreSQL service was listening on port 5432; CI runs it
against PostgreSQL 16.

## Verification commands

```text
ruff check app tests
pytest -q
alembic upgrade head
alembic downgrade base
alembic upgrade head
npm run lint
npm run build
pip-audit
npm audit --omit=dev --audit-level=high
```

CI runs the same backend PostgreSQL migration cycle, tests, Ruff, the isolated
PostgreSQL benchmark and dependency audit, plus the frontend lint/build and npm
audit. Docker smoke remains dependent on a host with a Docker engine.

## Roadmap

1. Obtain and verify one licensed market-data/index entitlement, then import all
   four indices with source, rights and session metadata.
2. Expand securities master through an authorized exchange/provider export.
3. Add market-cap, actual trading-value and foreign-flow fields only when the
   provider contract supplies them.
4. Connect an entitled financial-statement provider or continue the audited CSV
   workflow; keep automatic BCTC status `BLOCKED` until a real request succeeds.
5. Add a production scheduler/worker, official holiday calendar and multi-worker
   rate-limit backend before claiming production realtime coverage.

# V4 baseline audit

Date: 2026-10-12 (Asia/Bangkok)

## Repository and architecture

- Baseline commit: `00cc358` (V3 merged into `origin/main`).
- API: FastAPI + SQLAlchemy/Alembic under `apps/api`.
- Web: Next.js/React/TypeScript under `apps/web`.
- Storage: SQLite for local development and PostgreSQL in Compose.
- Connector boundary: market providers implement `MarketDataConnector`; RSS and FireAnt have separate explicit boundaries.

## Existing implemented modules

- Securities master with authorized CSV import and Vietnamese normalization.
- Yahoo development price connector, OHLCV normalization, provenance and persistent price storage.
- Technical-v2 indicators and independent component scores.
- Authorized financial-statement CSV ingestion, deterministic ratios and relative valuation.
- Metadata-only RSS news ingestion, event grouping and evidence fields.
- Optional analyst endpoint with deterministic fallback and OpenAI-compatible adapter.
- Idempotent job records, retries, watchlists and alert-rule persistence.
- Bearer admin/reader boundary, fixed-window limits, audit logs and trusted hosts.

## Baseline checks

- `apps/api`: `ruff check .` had two import-format findings in migrations; `pytest -q` passed 19 tests.
- `apps/web`: `npm run lint` passed; `npm run build` passed.
- Clean Alembic upgrade through `0006` was previously verified.
- Docker engine was not available in the execution environment.

## Confirmed V4 risks

1. Valuation persistence was publicly reachable through the calculation endpoint.
2. Job claiming was not atomic and could execute twice under concurrent workers.
3. Production secret/host configuration was not validated at settings load.
4. LLM requests lacked a dedicated request limit and audit event.
5. Financial/news/social coverage remains limited by licenses and credentials.

## Environment restrictions and integrations

- Yahoo is a non-official development source; commercial redistribution rights are not established.
- FireAnt calls remain blocked unless a real token and entitlement are configured.
- No licensed live financial provider, VPS API, social-platform authorization or production scheduler was supplied.
- GitHub is reachable for branch synchronization; Docker and registry security scans require external runtime/network access.

## Risk priorities

- P0: authorization of persistent writes, atomic job claims, no fabricated financial values.
- P1: provider licensing/coverage, claim verification, production worker and notification delivery.
- P2: full-market registry synchronization, advanced peer/DCF models and UX breadth.

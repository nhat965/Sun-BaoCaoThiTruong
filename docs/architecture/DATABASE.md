# Database

Alembic `0001` creates the MVP audit schema. Migration `0002` adds a database-backed securities master, complete OHLCV storage, validation/adjustment metadata, indexes, a natural uniqueness constraint and source-health records.

- `securities`: symbol, normalized name, aliases, exchange, classification, listing state, provider IDs and source/update metadata.
- `price_observations`: one row per security/provider/timestamp/interval with OHLCV, market and ingestion timestamps, validation state and adjustment policy.
- `analysis_runs`: formula version, coverage and serialized provenance for each completed analysis.
- `generated_reports`: report audit record/storage key.
- `source_health`: last known connector health and consecutive failures.
- `audit_logs`: actor, action, outcome, source IP and bounded metadata for privileged writes.
- `financial_periods`: reporting period, type, publication date, unit, source and verification state.
- `financial_statement_items`: normalized income/balance/cash-flow items per period.
- `financial_metrics`: reproducible calculated ratios and formula version.
- `valuation_results`: scenario values and the assumptions used.
- `corporate_actions`: source-backed action records reserved for future adjustment policies.

`PriceRepository` performs incremental upserts against `uq_price_point`; repeated requests update a point instead of multiplying rows. Production schema changes use Alembic. `Base.metadata.create_all` remains a local/test convenience only.

For an unversioned legacy MVP database, run `python scripts/adopt_legacy_database.py` before `alembic upgrade head`. The script refuses unknown layouts and stamps only a verified baseline or already-complete V2 schema.

V4 adds audit-safe valuation persistence and atomic automation state transitions. `jobs.status` is `QUEUED`, `RUNNING`, `RETRY_PENDING` or `FAILED/SUCCESS`; a unique idempotency key prevents duplicate scheduled rows and `job_runs` records execution attempts.

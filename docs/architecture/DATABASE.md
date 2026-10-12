# Database

Alembic `0001` creates the MVP audit schema. Migration `0002` adds a database-backed securities master, complete OHLCV storage, validation/adjustment metadata, indexes, a natural uniqueness constraint and source-health records.

- `securities`: symbol, normalized name, aliases, exchange, classification, listing state, provider IDs and source/update metadata.
- `price_observations`: one row per security/provider/timestamp/interval with OHLCV, market and ingestion timestamps, validation state and adjustment policy.
- `analysis_runs`: formula version, coverage and serialized provenance for each completed analysis.
- `generated_reports`: report audit record/storage key.
- `source_health`: last known connector health and consecutive failures.

`PriceRepository` performs incremental upserts against `uq_price_point`; repeated requests update a point instead of multiplying rows. Production schema changes use Alembic. `Base.metadata.create_all` remains a local/test convenience only.

For an unversioned legacy MVP database, run `python scripts/adopt_legacy_database.py` before `alembic upgrade head`. The script refuses unknown layouts and stamps only a verified baseline or already-complete V2 schema.


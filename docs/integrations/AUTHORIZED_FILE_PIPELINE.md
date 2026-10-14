# Authorized OHLCV file pipeline

The API accepts a CSV only when an administrator supplies the file and confirms the
source is permitted for this use. It does not download an exchange feed, infer
missing values, or calculate trading value from `close * volume`.

## Schema

Use [`authorized_ohlcv.csv`](../../apps/api/templates/authorized_ohlcv.csv) as the
header template. Required fields are `symbol`, `trading_date`,
`market_timestamp` (timezone required), OHLC, `volume`, and `retrieved_at`.
Optional `actual_trading_value` and `market_cap` remain null when the source does
not provide them. If present, `source_url` must be HTTPS and `validation_status`
must be `valid` or `partial`.

`trading_date` is checked against the Vietnam market timezone. Invalid rows are
rejected; valid rows are normalized to UTC and written through the same provider and
session uniqueness constraints used by API connectors. Replaying the same file is
idempotent (`skipped` rows increase and no duplicate observation is created).

## API and CLI

- `POST /api/v1/market/prices/import/preview` validates without database writes.
- `POST /api/v1/market/prices/import` requires the admin bearer token and records a
  `DataSyncRun` plus audit event.
- `python scripts/import_authorized_market_data.py FILE --preview` performs the
  same read-only validation locally; omit `--preview` to import.

The resulting observations are marked `source_mode=authorized` and
`freshness=historical_or_delayed`. They must never be presented as realtime merely
because the file was recently uploaded.

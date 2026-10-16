# Data coverage

`GET /api/v1/data-quality/coverage` calculates counts from persisted database rows. It
reports active securities by exchange, latest OHLCV session/provider/retrieval timestamp,
20/50/200-session depth, stale warnings, validation errors, actual trading value and
market-cap coverage, expected index availability, financial statement coverage, and
persisted source health.

`foreign_flow_rows=0` is accompanied by `foreign_flow_status=unavailable`; zero is not
presented as a measured market flow. Missing index sessions are `null` until an official
exchange calendar is authorized. Four calendar days is a warning only and is not proof of
staleness across holidays. Fixture and authorized-file rows retain their provenance.

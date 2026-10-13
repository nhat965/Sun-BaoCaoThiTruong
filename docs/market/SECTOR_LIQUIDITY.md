# Sector and liquidity intelligence — PR-C

PR-C uses the sector/industry taxonomy already stored in the securities registry. It does
not infer an industry from a ticker symbol. Every sector result carries taxonomy coverage,
eligible-period counts and limitations.

## Metrics

- Sector performance is an equal-weight mean of canonical security returns over 1, 5 and
  20 sessions; a symbol is eligible only when that many sessions are present.
- Relative volume is current volume divided by the mean volume of the previous 20 sessions.
- Relative strength is sector 1D performance minus VN-Index 1D performance. It is `null`
  until an authorized VN-Index observation exists.
- `actual_trading_value` is summed only when supplied by the provider. No `close × volume`
  estimate is stored or displayed as actual value.
- Liquidity concentration exposes top-5/top-10 volume shares. Trading-value concentration
  remains `null` when actual trading values are unavailable, and volume share is not treated
  as index contribution.

Sector rotation language is deliberately descriptive: performance and relative-volume
changes are proxies and do not prove money moved from one sector to another. Foreign net
trading remains `null` until an authorized feed supplies venue, trade type, session and
value/volume fields.

## API and persistence

- `GET /api/v1/market/sectors?sort_by=performance_1d|liquidity|breadth|relative_strength`
  returns ranked sectors and taxonomy/data coverage.
- `GET /api/v1/market/sectors/{sector_id}` returns a sector drilldown using the same
  formulas and explicit missing-data fields.
- `GET /api/v1/market/liquidity` returns market volume windows, relative volume, leaders,
  volume concentration and actual-value/foreign-flow status.
- `sector_snapshots` and `liquidity_snapshots` upsert by market session and formula version.

Migration `0019_sector_liquidity_intelligence` is additive and has an explicit downgrade.

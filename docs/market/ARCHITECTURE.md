# Market Intelligence architecture — PR-A/PR-B foundation

PR-A establishes the market-data contract used by later breadth, sector, risk and report
features. It deliberately separates source records from derived analytics.

## Storage boundaries

- `securities` is the persisted universe. It contains exchange, listing status, sector,
  industry, provider identifiers and registry provenance.
- `price_observations` stores normalized OHLCV observations. A row carries provider ID,
  provider symbol, Vietnam market session date, retrieval time, validation status,
  adjustment policy, source URL, coverage and freshness. Optional actual trading value and
  market capitalization remain null until an authorized source supplies them.
- `market_index_observations` stores VN-Index, VN30, HNX-Index, UPCoM-Index and any
  authorized related index observations. The unique key is `(symbol, provider_id,
  market_session_date)`, so a replay cannot create a second canonical row.
- `market_breadth_snapshots` and `market_regime_snapshots` store derived results keyed by
  session and formula version; they retain coverage, warnings and limitations alongside
  the metrics.

## Trust and deduplication

`canonical_daily_prices()` selects one observation per security/session using explicit
provider priority, fixture-last ordering and validation status. It is the only source used
for market-universe history coverage. No market index or foreign flow is inferred from
stock OHLCV.

## Session semantics

`VietnamMarketCalendar` converts timezone-aware timestamps to `Asia/Ho_Chi_Minh`. Weekends
are deterministic non-trading days. Weekdays are `trading_candidate` only because an
official exchange holiday calendar is not connected; the system therefore does not label a
holiday gap as a missing candle.

## API boundaries

- `GET /api/v1/market/indices` returns stored index observations plus provenance, coverage,
  freshness and limitations.
- `POST /api/v1/market/indices/import` accepts only an authorized admin CSV; it validates
  source metadata, deduplicates replays and protects valid records from an invalid replay.
- `GET /api/v1/data-quality` exposes history-depth, exchange and index coverage without
  inventing a full-market denominator.
- `GET /api/v1/market/breadth` and `GET /api/v1/market/regime` expose deterministic
  breadth/trend results with explicit denominators and evidence. They never infer index,
  foreign-flow or actual trading-value data.

Migration `0017_market_data_foundation` is additive and has an explicit downgrade.

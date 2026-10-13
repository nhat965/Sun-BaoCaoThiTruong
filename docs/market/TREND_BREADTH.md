# Market breadth and trend — PR-B

PR-B derives breadth and a conservative regime label only from the canonical daily
price observation selected by PR-A. The denominator is explicit for every moving-average
percentage: only symbols with at least the requested number of sessions are eligible.

## Formulas

- Advance/Decline difference = `advancers - decliners`.
- Advance/Decline ratio = `advancers / decliners` when the decliner count is non-zero.
- `% above MA_N` = symbols with `close > mean(last N closes)` divided by symbols with at
  least N canonical sessions, multiplied by 100.
- A 20-session high/low counts a symbol when the latest close is respectively at or above
  the maximum, or at or below the minimum, of its latest 20 canonical sessions.
- Realized volatility uses the population standard deviation of available daily returns,
  annualized by `sqrt(252)`. It is descriptive and is not a forecast probability.

## Regime rules

`UPTREND` requires MA20 breadth >= 60%, MA50 >= 55% and MA200 >= 50%; `DOWNTREND`
requires the corresponding values <= 40%, <= 45% and <= 50%. A realized volatility of
at least 45% annualized is labelled `VOLATILE`. If current-session coverage is below 50%,
MA50/MA200 are unavailable, or fewer than five symbols qualify for MA200, the result is
`UNCERTAIN`; all other sufficiently covered states are `SIDEWAYS`.

The regime response includes supporting evidence, conflicting signals, coverage and a
limitation that the rules are not a calibrated probability model. VN-Index divergence is
only emitted when an authorized VN-Index observation exists; no index, foreign flow or
trading value is inferred from stock OHLCV.

## API and persistence

- `GET /api/v1/market/breadth` returns current A/D, MA breadth, 20-session extremes,
  historical points, coverage, provenance and limitations.
- `GET /api/v1/market/regime` returns the conservative regime and its evidence/conflicts.
- `market_breadth_snapshots` and `market_regime_snapshots` use a unique
  `(market_session_date, formula_version)` key and are upserted on repeated reads.

Migration `0018_market_breadth_trend` is additive and has an explicit downgrade.

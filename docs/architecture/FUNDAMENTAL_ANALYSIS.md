# Fundamental analysis pipeline

The V3 financial path is deliberately source-first:

```text
authorized CSV/provider → validated financial periods/items → deterministic metrics → labeled valuation
```

CSV rows must include `period_end`, `period_type` (`quarter`, `year`, or `ttm`), `fiscal_year`, `statement_type` (`income`, `balance`, or `cash_flow`), `item_code`, and numeric `value`. Optional source URL, publication timestamp, unit, currency and verification status are preserved. Unknown period or statement types are rejected.

The latest stored period is selected and metrics are calculated from stored items, not from a client-supplied precomputed ratio. When a prior same-type period exists, revenue/net-income growth and average-balance ROE/ROA are calculated. Missing values remain `null` with warnings.

Implemented metrics include revenue/net-income growth, ROE, ROA, ROIC, gross/operating/net margin, EPS, BVPS, P/E, P/B, P/S, EV/EBITDA, D/E, current ratio, interest coverage, operating cash flow and free cash flow. P/E is unavailable for non-positive earnings; P/B is unavailable for non-positive equity.

Relative valuation accepts explicit EPS, BVPS, P/E and P/B assumptions and returns bull/base/bear values. Assumptions are labeled and stored with valuation results. No revenue forecast, WACC, peer multiple or target price is invented. DCF, historical bands and peer comparison remain blocked until verified datasets are connected.

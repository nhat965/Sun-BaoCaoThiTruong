# Risk & Scenario Engine

`GET /api/v1/market/risks` and `GET /api/v1/market/scenarios` are evidence-first outputs built from the canonical breadth, regime, and liquidity engines.

Risk signals expose a stable identifier, severity, trigger and threshold, observed evidence, and limitations. The engine covers trend/regime, breadth, liquidity, regime conflict, and data-quality coverage. A signal is not a forecast and does not include an uncalibrated probability.

Scenarios are conditional paths for `1-5 sessions` and `1-4 weeks` (`positive`, `base`, `negative`). Each path states assumptions, current evidence, invalidation conditions, risks, and what to watch. The engine intentionally omits target prices and probabilities because it has not been backtested/calibrated. Missing index, foreign-flow, or stale/partial price data is surfaced in `limitations` and never filled with synthetic values.

Snapshots are upserted by market session, scenario/signal id, and formula version (`market-risk-v1`, `market-scenario-v1`) so repeated reads do not create duplicates.

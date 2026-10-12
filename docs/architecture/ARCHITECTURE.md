# Architecture

The system is a modular monolith. FastAPI owns connector orchestration, normalization, deterministic analytics, reporting and persistence. Next.js is a presentation client and never calculates critical financial values.

```text
Browser → /api/v1 → AnalysisService → ConnectorManager → Yahoo
                              │              └────────→ provider circuit state
                              ├──────→ OHLCV normalization/validation
                              ├──────→ Technical + fundamental + valuation engines
                              ├──────→ Registry + incremental SQL storage
                              ├──────→ Admin-authenticated CSV ingestion + audit log
                              ├──────→ RSS news metadata
                              └──────→ PDF renderer
```

Connectors return canonical schemas. `AnalysisService` tolerates news failure while treating price failure as fatal. Reports consume the same structured analysis schema returned to the browser, preventing narrative/data drift.

`MarketDataConnector` is the provider boundary. The manager applies configured priority, records consecutive failures in its process-local circuit state, and never selects fixture data implicitly. A provider is not described as live until a real request succeeds.

Privileged CSV routes use an explicit Bearer admin token from environment configuration, constant-time comparison, reader/admin role separation, fixed-window rate limiting and audit events. The circuit registry is shared across `ConnectorManager` instances, with closed/open/half-open transitions and persisted source-health summaries.

All analytical numbers are deterministic. `technical-v2` exposes separate trend, momentum, volume-confirmation and volatility-risk scores instead of counting positive/negative labels. See [technical formulas](TECHNICAL_ANALYSIS.md).

Financial statements are normalized into periods and statement items before ratios are calculated. The selected period type (`quarter`, `year`, or `ttm`), source and reporting date are returned with metrics. Relative valuation requires explicit user assumptions and labels them; no forecast values are generated implicitly.

## Trust boundaries

- Upstream JSON/XML and article text are untrusted data.
- Numerical output is produced only by deterministic functions.
- Secrets remain server-side environment variables.
- CORS is restricted to the configured web origin.

## V4 hardening

State-changing routes are admin-protected, while public valuation is calculation-only. Persistent valuation uses a separate admin route. Jobs use database compare-and-set claims so multiple workers cannot execute one queued job twice. The analyst is an optional provider adapter over deterministic internal tools and never owns financial calculations.

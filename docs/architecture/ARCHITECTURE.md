# Architecture

The system is a modular monolith. FastAPI owns connector orchestration, normalization, deterministic analytics, reporting and persistence. Next.js is a presentation client and never calculates critical financial values.

```text
Browser → /api/v1 → AnalysisService → ConnectorManager → Yahoo
                              │              └────────→ provider circuit state
                              ├──────→ OHLCV normalization/validation
                              ├──────→ Technical + fundamental formula engines
                              ├──────→ Registry + incremental SQL storage
                              ├──────→ RSS news metadata
                              └──────→ PDF renderer
```

Connectors return canonical schemas. `AnalysisService` tolerates news failure while treating price failure as fatal. Reports consume the same structured analysis schema returned to the browser, preventing narrative/data drift.

`MarketDataConnector` is the provider boundary. The manager applies configured priority, records consecutive failures in its process-local circuit state, and never selects fixture data implicitly. A provider is not described as live until a real request succeeds.

All analytical numbers are deterministic. `technical-v2` exposes separate trend, momentum, volume-confirmation and volatility-risk scores instead of counting positive/negative labels. See [technical formulas](TECHNICAL_ANALYSIS.md).

## Trust boundaries

- Upstream JSON/XML and article text are untrusted data.
- Numerical output is produced only by deterministic functions.
- Secrets remain server-side environment variables.
- CORS is restricted to the configured web origin.


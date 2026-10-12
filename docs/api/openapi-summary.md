# API contract summary

- `GET /api/v1/health` — liveness and data mode.
- `GET /api/v1/sources` — capability and availability declarations.
- `GET /api/v1/sources/status` — active connector status; FireAnt stays blocked without a token.
- `GET /api/v1/stocks/search?q=HPG` — canonical security matches.
- `GET /api/v1/securities` — database-filtered securities explorer with pagination, facets, sorting and nullable latest market/fundamental fields.
- `GET /api/v1/stocks/{symbol}` — security metadata.
- `GET /api/v1/stocks/{symbol}/prices?limit=260` — canonical OHLCV.
- `GET /api/v1/stocks/{symbol}/technicals` — latest deterministic indicators.
- `GET /api/v1/stocks/{symbol}/news` — related article metadata.
- `GET /api/v1/stocks/{symbol}/analysis` — complete research view.
- `POST /api/v1/stocks/{symbol}/reports` — PDF bytes.
- `POST /api/v1/securities/import` — authorized CSV import into the securities master.
- `POST /api/v1/securities/import/xlsx` — authorized XLSX import through the same validation/upsert path.
- `POST /api/v1/stocks/{symbol}/financials/import` — admin-only validated financial-statement CSV import.
- `GET /api/v1/stocks/{symbol}/fundamentals` — ratios calculated from stored statements and latest stored price.
- `POST /api/v1/fundamentals/calculate` — deterministic ratios from supplied financial inputs.
- `POST /api/v1/fundamentals/valuation` — relative P/E + P/B scenarios using explicit labeled assumptions.
- `POST /api/v1/analyst/chat` — grounded analyst response with tool outputs and evidence; optional OpenAI-compatible provider.
- `POST /api/v1/jobs/eod/{symbol}`, `GET /api/v1/jobs`, `POST /api/v1/jobs/{id}/run` — idempotent EOD job lifecycle.
- `POST /api/v1/watchlists`, `/items`, `/rules` — admin-protected watchlist and deterministic alert-rule setup.

State-changing import routes require `Authorization: Bearer <ADMIN_API_TOKEN>`. Missing credentials returns `401` (or `503` when server-side admin auth is not configured), a reader token returns `403`, and malformed CSV schema returns `422`.

Interactive OpenAPI documentation is served at `/docs`.


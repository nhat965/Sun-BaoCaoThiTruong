# API contract summary

- `GET /api/v1/health` — liveness and data mode.
- `GET /api/v1/sources` — capability and availability declarations.
- `GET /api/v1/sources/status` — active connector status; FireAnt stays blocked without a token.
- `GET /api/v1/stocks/search?q=HPG` — canonical security matches.
- `GET /api/v1/stocks/{symbol}` — security metadata.
- `GET /api/v1/stocks/{symbol}/prices?limit=260` — canonical OHLCV.
- `GET /api/v1/stocks/{symbol}/technicals` — latest deterministic indicators.
- `GET /api/v1/stocks/{symbol}/news` — related article metadata.
- `GET /api/v1/stocks/{symbol}/analysis` — complete research view.
- `POST /api/v1/stocks/{symbol}/reports` — PDF bytes.
- `POST /api/v1/securities/import` — authorized CSV import into the securities master.
- `POST /api/v1/fundamentals/calculate` — deterministic ratios from supplied financial inputs.

Interactive OpenAPI documentation is served at `/docs`.


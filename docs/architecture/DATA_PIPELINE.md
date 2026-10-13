# Data pipeline contract

## Provider capability model

The runtime uses these explicit capabilities and never probes an undeclared method:

- `securities_metadata`
- `historical_ohlcv`
- `market_indices`
- `corporate_actions`
- `income_statement`
- `balance_sheet`
- `cash_flow_statement`

Each provider publishes documented capabilities separately from enabled capabilities.
Documented means an official source describes the feature. Enabled means this deployment
has the required credentials/entitlement and an implemented connector. `available` is only
reported after a successful real request; configured-but-untested remains `configured`.

## HTTP contract

### `GET /api/v1/providers`

Returns the provider catalog with official documentation URL, authentication, access and
licensing requirements, documented/enabled capabilities, availability, last successful
request and a truthful test result.

### `POST /api/v1/sync/prices/{symbol}`

Admin-only. Query parameters:

- `provider`: `auto` (default) or an enabled provider identifier.
- `mode`: `auto`, `initial`, or `incremental`.
- `limit`: 30–520 observations.

The response is a persisted sync run. `auto` selects only a provider with
`historical_ohlcv`. Incremental mode uses the latest stored provider timestamp as its
cursor. The price uniqueness key remains `(security_id, provider, market_timestamp,
interval)`, so replaying a run cannot create duplicates.

### `POST /api/v1/sync/financials/{symbol}`

Admin-only. Requests an automatic BCTC sync. If no provider has all three statement
capabilities enabled, the operation is persisted and returned as `BLOCKED`; no guessed
endpoint is called.

### `GET /api/v1/sync/runs`

Returns recent persisted runs, optionally filtered by symbol, provider, capability or
status. Errors are recorded separately and counted by data-quality diagnostics.

### `GET /api/v1/stocks/{symbol}/financial-statements`

Returns normalized statement periods and the required raw line items with report period,
fiscal quarter/year, consolidated/separate scope, original/amended status, normalized unit,
original unit/value, source URL, verification status and update timestamp. Missing items are
omitted and the client renders `Chưa có dữ liệu`; the API does not synthesize values.

## Ingestion rules

1. Normalize timestamps to UTC and financial currency values to VND while retaining raw
   value/unit.
2. Preserve provider identity and retrieval/report timestamps on every stored record.
3. Upsert only through natural uniqueness constraints; report inserted/updated/skipped.
4. Never replace a `verified` financial period or item with `unverified` input.
5. Persist `RUNNING`, `SUCCESS`, `PARTIAL`, `FAILED`, or `BLOCKED` for every sync attempt.
6. Fixture data remains visibly marked and is never selected implicitly in production.

## Source survey

| Source | Official documentation | Supported data | Authentication | Access / terms | Practical connection | Verification result | Cost / limits |
|---|---|---|---|---|---|---|---|
| FireAnt REST API v1 | <https://api.fireant.vn/> | Documented scopes include symbols, companies and finance | OAuth2 bearer token with explicit scopes | FireAnt account, granted scopes and applicable data agreement are required | Connector remains gated; no data endpoint is enabled without a supplied token and verified entitlement | `BLOCKED` in this environment; only service health can be checked when a token exists | Public price not verified |
| SSI FastConnect API v3 | <https://developers.ssi.com.vn/docs/getting-started/overview> | Securities metadata, daily/intraday OHLCV and market indices | API key + secret exchanged for Bearer JWT | SSI account, FastConnect registration/approval and acceptance of service terms | Official interface is suitable for a future licensed connector; credentials were not supplied | `BLOCKED` in this environment; no authenticated request made | Per-key rate limits are returned in headers; daily history from listing date, intraday history one year; public price not verified |
| FiinGroup API Datafeed | <https://datafeed.fiingroup.vn/> | Company profile, market data, corporate events and detailed consolidated/separate BCTC | Commercial credentials; public documentation does not establish a reusable anonymous flow | Contract/entitlement and redistribution terms must be obtained from FiinGroup | Schema is documented, but no credential or commercial permission is present | `BLOCKED`; no provider request made | Contact provider; public price not verified |
| HOSE/HNX public disclosure portals | <https://www.hnx.vn/co-phieu-etfs/chung-khoan-ny.html> | Listing/disclosure documents and issuer filings | Public browsing plus issuer workflows | No documented bulk API or automated redistribution permission was verified for this project | Used only as a provenance link for operator-authorized files; no scraping/internal endpoint use | `BLOCKED` for automatic sync | Not verified |
| User-authorized files | Repository import documentation | Securities CSV/XLSX, financial CSV and corporate-action CSV | Application admin bearer token | Operator confirms lawful access and source provenance | Implemented and testable now | `AVAILABLE` when a valid file is submitted | No provider fee; application size/rate limits apply |
| Yahoo Finance chart connector | Existing development connector; Yahoo terms apply | Delayed historical OHLCV | None | No commercial redistribution entitlement is asserted | Implemented for development and real connectivity checks; not a licensed production feed | Real HPG/FPT calls must succeed before being marked available | Upstream limits are undocumented for this connector |

No exchange-internal endpoint, mobile endpoint, reverse-engineered session or undocumented
provider route is part of this contract.

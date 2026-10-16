# SSI FastConnect Data SDK

## Source and entitlement boundary

The integration targets SSI's public Python SDK repository:

- SDK: <https://github.com/SSI-Securities-Corporation/python-fcdata>
- SSI developer documentation: <https://developers.ssi.com.vn/docs/getting-started/overview>
- Official FastConnect Data host used by the SDK: `https://fc-data.ssi.com.vn/`

The SDK documents the following Data API methods used by this project:

| Capability | Official SDK method | Status in this repository |
| --- | --- | --- |
| Securities master | `MarketDataClient.securities` / `model.securities` | Implemented, credential-gated |
| Security details | `MarketDataClient.securities_details` | Provider boundary only |
| Historical OHLCV | `MarketDataClient.daily_ohlc` / `model.daily_ohlc` | Implemented, credential-gated |
| Index list/components | `index_list`, `index_components` | Provider boundary only |
| Historical index | `MarketDataClient.daily_index` / `model.daily_index` | Implemented, credential-gated |

The application uses the official `ssi-fc-data` package when credentials are
configured and no custom endpoint override is present. It does not infer an SSI
URL from an undocumented web endpoint. Missing package, credentials, account
approval, response entitlement, or redistribution permission produces `BLOCKED`
and writes no market data.

## Configuration

```dotenv
MARKET_PROVIDER_PRIORITY=ssi_fastconnect,yahoo
SSI_DATA_BASE_URL=https://fc-data.ssi.com.vn/
SSI_API_KEY=<consumerID>
SSI_API_SECRET=<consumerSecret>
```

Secrets belong in the deployment secret store. They must not be committed or
printed in logs. The provider is marked live only after a request succeeds and
the normalized rows are persisted with SSI provenance.

## Backfill and incremental sync

- `POST /api/v1/sync/securities?provider=ssi_fastconnect&markets=HOSE,HNX,UPCOM`
  backfills the securities master and records a `DataSyncRun`.
- `POST /api/v1/sync/prices/{symbol}?provider=ssi_fastconnect&mode=initial`
  performs the first OHLCV sync.
- The same endpoint with `mode=incremental` uses the latest persisted provider
  session as the cursor. Database uniqueness and `PriceRepository` counts make a
  replay idempotent.
- `POST /api/v1/sync/indices?provider=ssi_fastconnect` persists official
  DailyIndex observations for VN-Index, VN30, HNX-Index and UPCoM-Index when SSI
  returns them; missing series are not synthesized.
- CSV/XLSX import endpoints remain independent of this SDK and remain usable
  when SSI is unavailable.
- The CSV/XLSX registry importer initializes the local schema when used as a
  standalone operator utility, so it does not require a prior API request or an
  installed commercial provider.

## Acceptance evidence

The repository tests mock the official SDK boundary without contacting SSI. A
production acceptance run still requires operator-supplied credentials and
permission. Until that run is recorded, this provider remains configured but
not verified; the project must not claim full-market realtime coverage.

# SSI FastConnect V3 operator setup

The repository records SSI as a provider boundary only. The documented token
exchange is `POST /api/v3/auth/token` with JSON fields `apiKey` and `apiSecret`.
Market-data services are documented separately by SSI (for example daily OHLC,
indexes and securities information). We do not infer undocumented endpoints.

## Configuration

```dotenv
SSI_BASE_URL=https://api.ssi.com.vn
SSI_AUTH_URL=https://api.ssi.com.vn/api/v3/auth/token
SSI_ENVIRONMENT=production
SSI_API_KEY=                 # secret store only
SSI_API_SECRET=              # secret store only
```

SSI UAT and production credentials are separate. Market-data access does not need
an OTP according to the SDK documentation, but account approval and applicable
service terms still apply. Keep API keys, secrets and Bearer tokens out of logs and
source control. The provider exposes rate-limit headers; ingestion must respect
them before an adapter is enabled.

## Current status

`verify_ssi_connection.py` is a credential-independent diagnostic. Without both
credentials it returns `BLOCKED` and exits successfully so CI does not need secrets.
With approved credentials it performs only the documented token request and reports
the status without storing the token. Historical OHLCV and index adapters remain
disabled until an authenticated integration test proves the response schema and
the operator confirms redistribution rights.

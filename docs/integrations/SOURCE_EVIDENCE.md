# Authorized market-data source evidence

This document is the operator record for Task 04. A provider is marked **live** only
after a real request succeeds with credentials and the response is persisted with
provenance. Documentation links are evidence of a documented capability, not proof
that this deployment has access to the data.

| Source | Official documentation | Supported data | Authentication / rights | This deployment | Cost / limits |
| --- | --- | --- | --- | --- | --- |
| SSI FastConnect V3 | [Overview](https://developers.ssi.com.vn/docs/getting-started/overview), [auth token](https://developers.ssi.com.vn/docs/api-reference/auth-token), [Python service classes](https://developers.ssi.com.vn/docs/sdk/python/service-classes) | Securities metadata, daily OHLC, indexes and summaries | SSI account, Developer Portal approval, API key + secret; keep credentials outside git | **BLOCKED** until `SSI_API_KEY` and `SSI_API_SECRET` are supplied and an authenticated test succeeds | Per-key rate-limit response headers; production/UAT are separate |
| FiinGroup Datafeed | [Enterprise API](https://datafeed.fiingroup.vn/api-doanh-nghiep), [financial statements](https://datafeed.fiingroup.vn/api-doanh-nghiep/bao-cao-tai-chinh-bctc), [original reports](https://datafeed.fiingroup.vn/api-doanh-nghiep/bao-cao-tai-chinh-bctc/file-bctc-goc/tai-lieu-goc-bao-cao-tai-chinh) | Enterprise metadata and financial statements (including consolidated/separate variants) | Commercial contract, API credentials, entitlement and redistribution terms | **BLOCKED**; endpoint and schema are not enabled from guesses | Provider contract required; public quota/price not verified |
| HNX public disclosure | [HNX portal](https://www.hnx.vn/) | Public disclosure documents when an operator downloads them lawfully | Human/operator download and terms of use must be recorded for each file | **MANUAL / BLOCKED for unattended pull** | No automated entitlement assumed |
| Authorized CSV/XLSX | Operator-provided file and provenance URL | OHLCV, index, securities and financial records according to the template | Admin bearer token plus written authorization for the source | **AVAILABLE** as an explicit import path; no network fetch is implied | Size and admin rate limits; source rights remain with operator |
| Yahoo chart fallback | [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) | Development OHLCV fallback only | No application credential; redistribution rights are not asserted | **DEVELOPMENT ONLY** and must be labeled | Quota and production entitlement unverified |

## Operator verification

1. Copy `.env.example` to a secret store-backed environment; never commit a key,
   secret, JWT, or downloaded protected response.
2. Run `python scripts/verify_ssi_connection.py --no-network` to inspect the local
   configuration without contacting SSI.
3. If an approved credential is present, run the same command without
   `--no-network`. The command only calls the documented token endpoint, redacts
   secrets, and reports `BLOCKED`/`FAILED`/`AVAILABLE`; it does not persist a token.
4. Record the response timestamp, HTTP status, rate-limit headers and operator
   entitlement in the deployment log before enabling an adapter.

No source is treated as realtime merely because a URL or credential is configured.

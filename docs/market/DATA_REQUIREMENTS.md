# Market data requirements — PR-A

| Dataset | Required provenance | Current state |
|---|---|---|
| Securities master | source name/URL, retrieval time, exchange, listing status, provider IDs | PARTIAL: authorized bootstrap/import path; not full-market |
| Daily OHLCV | provider, provider symbol, market session, market timestamp, retrieved/updated time, mode, validation, adjustment policy | PARTIAL: Yahoo development connector is live for delayed history; commercial redistribution is unverified |
| Market indices | provider, source URL, session, timestamp, mode, validation, coverage, freshness, adjustment policy | BLOCKED until an authorized index feed or file is supplied; API returns unavailable, never inferred |
| Market capitalization | provider and as-of timestamp | BLOCKED; nullable in price storage |
| Foreign flow | venue, trade type, volume/value, session and provider | BLOCKED; null rather than inferred |
| Exchange calendar | official holiday/session source and timezone | PARTIAL: weekend rule only; weekday is a candidate, not a confirmed session |

The expected index set is VN-Index, VN30, HNX-Index and UPCoM-Index. Coverage is reported
as stored symbols divided by that expected set, not as a claim that missing indices are flat.

An index CSV must contain at least:

```text
symbol,name,exchange,market_session_date,market_timestamp,close,provider,retrieved_at,data_mode,validation_status
```

Optional columns include `previous_close`, `source_url`, `last_updated`, `coverage`,
`freshness` and `adjustment_policy`.

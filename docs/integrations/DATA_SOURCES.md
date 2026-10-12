# Data sources

## Yahoo Finance chart

Implemented as a replaceable, unauthenticated development connector. It resolves provider IDs from the securities registry, falling back to `.VN`, and records source URL, retrieval time, market time, freshness, currency, validation state and adjustment policy. It is not represented as a licensed commercial feed. Production must configure a contractual provider behind the same interface.

## VnExpress RSS

Implemented for public RSS metadata. The application stores/returns headline, publication timestamp, publisher and original URL only. Matching normalizes Vietnamese aliases, scores relevance, deduplicates titles and classifies a small deterministic event taxonomy. It is still keyword-based and may be incomplete.

## FireAnt

The official [FireAnt API documentation](https://api.fireant.vn/) advertises OAuth scopes including `companies-read`, `finance-read` and `posts-read`. The isolated connector can check the documented `/monitoring/status` endpoint when `FIREANT_ACCESS_TOKEN` is configured. Without a token it reports `unavailable` with a `BLOCKED` message and performs no request. A health response alone does not prove any data scope; market-data calls remain disabled until credentials, scopes, entitlements and redistribution rights are verified.

## Securities master

`app/data/securities_bootstrap.csv` is a visibly sourced, non-comprehensive bootstrap set. Operators can import an authorized CSV or XLSX; symbol, Vietnamese name/aliases, exchange, status, provider IDs and provenance are persisted without code changes. HNX provides an [official listing page](https://www.hnx.vn/co-phieu-etfs/chung-khoan-ny.html), but the application does not scrape it without confirmed automated-use and redistribution permission.

## Corporate actions and price quality

Authorized action exports can be stored with source, effective timestamp, ratio/cash amount and verification status. They are not automatically applied to historical prices. Price observations retain explicit adjusted/unadjusted provenance plus flags for zero volume, a jump over 20%, or a calendar gap over four days. The calendar-gap flag is a review signal, not proof of a missing session, because an official exchange holiday calendar is not yet connected.

## Financial statements

`POST /stocks/{symbol}/financials/import` accepts an authorized CSV with period, statement type, normalized item code, value, source, reporting and verification metadata. The system stores periods/items first, then calculates ratios from stored rows. No endpoint labels a manual/CSV source as live. A provider interface is reserved for FireAnt or another licensed feed; it remains disconnected until a real authorized request succeeds.

## VPS SmartOne

No connector is implemented. The product will prefer manual/CSV portfolio import until an official, documented, read-only integration is available. It will not reverse-engineer login or trading endpoints.

V4 source rule: a feed is operational only after a real request succeeds. `NEWS_FEEDS` may list authorized RSS URLs, but configured-only URLs are reported as unverified and do not count as live coverage. Yahoo remains a development source without a commercial licensing claim; FireAnt, VPS and live financial/social providers remain credential or entitlement dependent.

## Data-quality diagnostics

`GET /api/v1/data-quality` reports securities coverage, stored price-observation coverage, latest market/retrieval timestamps, and connector health. Migration `0007` retains each connector's latest successful and failed check independently, plus consecutive failures. The web dashboard presents `fixture`, `configured`, `available` and `unavailable` distinctly; configured sources without a verified successful request are not described as live.

## AI evidence boundary

External LLM responses are proposals, not a data source. A proposed financial claim is accepted only when its evidence ID resolves to the same security, metric, period and compatible unit/value. Forecasts additionally require evidence explicitly classified as a forecast. The application renders its own narrative from accepted claims and records rejected-claim limitations.

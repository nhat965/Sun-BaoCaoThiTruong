# Data sources

## Yahoo Finance chart

Implemented as a replaceable, unauthenticated development connector. It resolves provider IDs from the securities registry, falling back to `.VN`, and records source URL, retrieval time, market time, freshness, currency, validation state and adjustment policy. It is not represented as a licensed commercial feed. Production must configure a contractual provider behind the same interface.

## VnExpress RSS

Implemented for public RSS metadata. The application stores/returns headline, publication timestamp, publisher and original URL only. Matching normalizes Vietnamese aliases, scores relevance, deduplicates titles and classifies a small deterministic event taxonomy. It is still keyword-based and may be incomplete.

## FireAnt

An isolated connector can check the documented `/monitoring/status` endpoint when `FIREANT_ACCESS_TOKEN` is configured. Without a token it reports `unavailable` with a `BLOCKED` message and performs no request. Market-data capabilities remain unimplemented until credentials, scopes, entitlements and redistribution rights are verified by a successful real request.

## Securities master

`app/data/securities_bootstrap.csv` is a visibly sourced, non-comprehensive bootstrap set. Operators can import an authorized CSV through `POST /api/v1/securities/import`; symbol, Vietnamese name/aliases, exchange and provenance are persisted without code changes. No exchange page is scraped implicitly.

## Financial statements

`POST /stocks/{symbol}/financials/import` accepts an authorized CSV with period, statement type, normalized item code, value, source, reporting and verification metadata. The system stores periods/items first, then calculates ratios from stored rows. No endpoint labels a manual/CSV source as live. A provider interface is reserved for FireAnt or another licensed feed; it remains disconnected until a real authorized request succeeds.

## VPS SmartOne

No connector is implemented. The product will prefer manual/CSV portfolio import until an official, documented, read-only integration is available. It will not reverse-engineer login or trading endpoints.

V4 source rule: a feed is operational only after a real request succeeds. `NEWS_FEEDS` may list authorized RSS URLs, but configured-only URLs are reported as unverified and do not count as live coverage. Yahoo remains a development source without a commercial licensing claim; FireAnt, VPS and live financial/social providers remain credential or entitlement dependent.

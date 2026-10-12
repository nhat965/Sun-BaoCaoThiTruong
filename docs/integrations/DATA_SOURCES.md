# Data sources

## Yahoo Finance chart

Implemented as a replaceable, unauthenticated development connector. It resolves provider IDs from the securities registry, falling back to `.VN`, and records source URL, retrieval time, market time, freshness, currency, validation state and adjustment policy. It is not represented as a licensed commercial feed. Production must configure a contractual provider behind the same interface.

## VnExpress RSS

Implemented for public RSS metadata. The application stores/returns headline, publication timestamp, publisher and original URL only. Matching normalizes Vietnamese aliases, scores relevance, deduplicates titles and classifies a small deterministic event taxonomy. It is still keyword-based and may be incomplete.

## FireAnt

An isolated connector can check the documented `/monitoring/status` endpoint when `FIREANT_ACCESS_TOKEN` is configured. Without a token it reports `blocked` and performs no request. Market-data capabilities remain unimplemented until credentials, scopes, entitlements and redistribution rights are verified by a successful real request.

## Securities master

`app/data/securities_bootstrap.csv` is a visibly sourced, non-comprehensive bootstrap set. Operators can import an authorized CSV through `POST /api/v1/securities/import`; symbol, Vietnamese name/aliases, exchange and provenance are persisted without code changes. No exchange page is scraped implicitly.

## VPS SmartOne

No connector is implemented. The product will prefer manual/CSV portfolio import until an official, documented, read-only integration is available. It will not reverse-engineer login or trading endpoints.


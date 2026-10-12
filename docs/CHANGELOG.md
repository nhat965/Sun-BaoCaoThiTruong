# Changelog

## 0.3.0 — V3 hardening and fundamental research

- Protected securities and financial-statement imports with environment-configured Bearer admin auth, reader/admin authorization, fixed-window rate limiting and audit logs.
- Added shared closed/open/half-open connector circuit breaker with persisted source health.
- Added stricter OHLCV finite/positive/outlier validation and duplicate-collapse provenance notes.
- Added financial periods, normalized statement items, metrics, valuation results and corporate-action schema/migration.
- Added authorized financial CSV ingestion, stored-period ratio calculation and explicit relative P/E/P/B scenarios.
- Added fundamental metrics panel in the dashboard with source/period metadata and missing-data messaging.
- Added 4 security/fundamental integration tests; backend suite now has 18 tests.

## 0.2.0 — 2026-10-12

- Added persistent securities master with normalized Vietnamese search, aliases, provider IDs and authorized CSV import.
- Added canonical validated OHLCV normalization and incremental conflict-safe persistence.
- Added configurable provider orchestration and an honest token-gated FireAnt status adapter.
- Expanded deterministic technical indicators and replaced signal counting with component scores and conflict explanations.
- Added a deterministic fundamental-ratio calculator with safe unavailable states.
- Improved news matching, relevance scoring, title deduplication and event classification.
- Extended the dashboard and PDF with evidence, two-sided factors, scenarios and data limitations.
- Added Alembic V2 migration and a guarded legacy-database adoption utility.
- Expanded backend tests from 6 to 14 and documented live validation results.

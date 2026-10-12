# Changelog

## 0.4.1 — V4 M2 data-quality vertical slice

- Added `/api/v1/data-quality` with securities/price coverage, freshness and explicit source limitations.
- Added persisted latest-success/latest-failure connector timestamps in migration `0007`.
- Added a responsive Vietnamese data-quality dashboard with honest fixture/configured/unavailable states.
- Added regression coverage and verified backend lint/tests, clean migrations, frontend lint/build and desktop/mobile browser behavior.

## 0.4.0 — V4 M1 security and reliability hardening

- Split public valuation calculation from admin-only valuation persistence.
- Added atomic database job claims, retry-pending state and stale-running recovery.
- Added production configuration validation, global request-size limits and dedicated analyst rate limiting/audit metadata.
- Added V4 baseline, progress and security review documentation.
- Added concurrent execution, production-config and authorization regression tests; backend suite now has 21 tests.

## 0.3.0 — V3 hardening and fundamental research

- Protected securities and financial-statement imports with environment-configured Bearer admin auth, reader/admin authorization, fixed-window rate limiting and audit logs.
- Added shared closed/open/half-open connector circuit breaker with persisted source health.
- Added stricter OHLCV finite/positive/outlier validation and duplicate-collapse provenance notes.
- Added financial periods, normalized statement items, metrics, valuation results and corporate-action schema/migration.
- Added authorized financial CSV ingestion, stored-period ratio calculation and explicit relative P/E/P/B scenarios.
- Added fundamental metrics panel in the dashboard with source/period metadata and missing-data messaging.
- Added configurable metadata-only RSS connectors, normalized news/event persistence and safe FireAnt unsupported-operation boundaries.
- Added grounded analyst endpoint with optional OpenAI-compatible provider, explicit evidence kinds and deterministic fallback.
- Added idempotent EOD jobs/retries, job runs, watchlists and alert-rule persistence plus dashboard analyst panel.
- Added news/automation migrations `0005`/`0006`; backend suite now has 19 tests.

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

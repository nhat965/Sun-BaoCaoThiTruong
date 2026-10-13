# Financial Statements Engine V2 — PR-C test report

## Scope

PR-A covers canonical financial period metadata, versioned line-item mapping,
VND/unit normalization, YTD-to-quarter conversion helpers and migration
compatibility. PR-B adds deterministic validation/reconciliation and strict
rollback reporting. PR-C adds a versioned formula registry, input provenance,
sign-safe CAPEX/FCF, additional health metrics and period-level metadata.
Provider orchestration and frontend work remain deferred to PR-D through PR-F.

## Changes tested

- Migration `0015_financial_canonical_metadata` adds period boundaries,
  accounting standard, retrieval/validation timestamps, data version and
  content hash without removing existing rows.
- Existing statement/item rows are backfilled with `retrieved_at = updated_at`,
  `accounting_standard = unknown`, `financial-v1`, and their existing item code
  as `raw_item_code`.
- Provider aliases map to canonical item codes and preserve unknown codes.
- Quarter, year, YTD and TTM remain distinct; no YTD value is treated as a
  standalone quarter.
- Repeated imports continue to use the existing idempotent period/item keys.
- Validation reports include stable issue codes and retain rejected reports
  after strict transaction rollback.
- Metric formulas are registered under `fundamental-v3`; each result exposes
  required inputs, missing inputs, applicability, units and limitations.
- CAPEX is normalized to an absolute investment amount before FCF and CAPEX
  intensity are calculated. EPS prefers parent-attributable profit and diluted
  shares when available.
- Repository responses attach the statement period end to metric metadata.

## Baseline and PR-A results

- Baseline from PR #4 head: Ruff passed; backend pytest **66 passed, 1 warning**.
- PR-A targeted tests: **16 passed, 1 warning**.
- PR-B validation tests: **10 passed, 1 warning**.
- Full backend Ruff/pytest: **78 passed, 1 warning**.
- Frontend lint and production build: passed.
- SQLite migration upgrade → downgrade → upgrade through `0015`: passed.

## Explicitly deferred

Live provider activation and financial analysis UI belong to later PRs.
No live BCTC verification is claimed without authorized credentials and source
entitlement.

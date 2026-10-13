# Financial Statements Engine V2 — PR-A test report

## Scope

PR-A covers canonical financial period metadata, versioned line-item mapping,
VND/unit normalization, YTD-to-quarter conversion helpers and migration
compatibility. Validation/reconciliation, metrics, provider orchestration and
frontend work are intentionally deferred to PR-B through PR-F.

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

## Baseline and PR-A results

- Baseline from PR #4 head: Ruff passed; backend pytest **66 passed, 1 warning**.
- PR-A targeted tests: **16 passed, 1 warning**.
- Full backend Ruff/pytest: **70 passed, 1 warning**.
- Frontend lint and production build: passed.
- SQLite migration upgrade → downgrade → upgrade through `0015`: passed.

## Explicitly deferred

Accounting consistency and reconciliation reports, formula registry/TTM metric
engine, live provider activation and financial analysis UI belong to later PRs.
No live BCTC verification is claimed without authorized credentials and source
entitlement.


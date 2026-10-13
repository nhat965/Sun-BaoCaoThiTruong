# Financial Statements Engine V2 — canonical dictionary (PR-A)

PR-A adds provenance and period metadata to the existing `financial_periods`
and `financial_statement_items` tables. It does not create a parallel BCTC
store.

## Period metadata

| Field | Meaning |
| --- | --- |
| `period_start`, `period_end` | Inclusive reporting boundary. `period_start` is inferred only for an unambiguous calendar quarter/year/YTD; TTM requires an explicit source boundary. |
| `period_type` | `quarter`, `year`, `ytd`, or `ttm`. |
| `statement_scope` | `consolidated` or `separate`. |
| `statement_status` | `original` or `amended`; both versions can coexist. |
| `accounting_standard` | Provider-declared standard, default `unknown`. It is metadata, not an independent verification. |
| `currency`, `unit` | Currency and normalized unit. VND scale units are converted to base VND. |
| `reported_at` | Issuer/provider reporting time when supplied. |
| `retrieved_at` | Time the application obtained the payload. |
| `validated_at` | Reserved for a later validation step; never set merely because parsing succeeded. |
| `verification_status` | Human/source verification state; schema validity does not imply `verified`. |
| `data_version` | Canonical payload version (`financial-v1` by default). |
| `content_hash` | SHA-256 of the imported UTF-8 payload for replay detection and audit. |

## Line items

`item_code` is canonical and versioned by `mapping_version` (`financial-map-v1`).
`raw_item_code` preserves the provider label so a mapping can be reviewed or
replayed when a provider changes its taxonomy. Unknown labels are normalized to
a stable snake-case token instead of being silently dropped.

The current mapping includes revenue, cost of goods sold, gross profit,
operating income, profit before tax, tax expense, parent net income, assets,
liabilities, equity, cash, inventory, receivables, borrowings, cash-flow
categories, CAPEX and share-count fields.


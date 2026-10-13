# Financial validation rules (PR-B)

Validation is separate from source verification. A schema-valid payload is not
automatically `verified`.

## Statuses

- `valid`: all executed checks passed.
- `warning`: checks ran and found non-fatal provenance or reconciliation issues.
- `invalid`: a numeric, period, currency or accounting relationship is invalid.
- `insufficient_data`: a relationship could not be evaluated because required
  line items were not supplied.
- `rejected`: retained as a compatibility value for older import responses.

Each report stores `checks`, `errors`, `warnings` and structured `issues` with a
stable code, severity, message, item code and source name.

## Current checks

1. Period order, statement scope/status and three-letter currency.
2. Decimal finiteness and the database numeric range.
3. Non-negative total assets, total liabilities and share counts.
4. Balance equation `assets ≈ liabilities + equity` with a 0.1%/one-unit
   tolerance.
5. Gross profit reconciliation when revenue, cost of goods sold and gross
   profit are all present.
6. Cash-flow reconciliation when beginning/ending cash, CFO, CFI and CFF are
   all present; foreign-exchange effect is included when supplied.
7. Missing source URL and suspicious reporting timestamps are warnings.

Strict financial synchronization rolls back inserted periods/items when an
invalid report is produced, while retaining a report with `period_id = null`
for audit. Missing inputs never become zero and do not receive a verified label.


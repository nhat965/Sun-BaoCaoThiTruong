# Financial provider contract

Financial ingestion uses an explicit `FinancialStatementProvider` boundary.
The provider declares its identity and the statement capabilities it actually
implements before any request is made:

- `income_statement`
- `balance_sheet`
- `cash_flow_statement`

`AuthorizedCsvFinancialProvider` is the only enabled financial provider in this
environment. It accepts an operator-configured HTTPS URL template, validates an
exact host allowlist and the operator's lawful-use confirmation, then returns a
payload with provider identity, source host and retrieval timestamp. It does
not infer API paths or call undocumented endpoints.

The sync service persists every attempt in `data_sync_runs` and
`data_sync_errors`. Imports remain idempotent through the financial period/item
keys, and the repository validation/upsert rules prevent an unverified replay
from replacing an already verified value. FireAnt, SSI and FiinGroup remain
catalogued but disabled until credentials, scopes and entitlement are supplied
and a real authorized call succeeds.

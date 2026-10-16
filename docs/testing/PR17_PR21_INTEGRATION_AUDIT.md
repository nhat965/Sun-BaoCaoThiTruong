# PR #17–#21 integration audit

Audited against `origin/main` at `d2b428d` on 2026-10-15.

| PR | Head | Commit theme | Relationship to next PR | Safe action |
| --- | --- | --- | --- | --- |
| #17 | `4556242` | freshness/session hardening and PostgreSQL benchmark evidence | ancestor of #18 | integrate once; do not cherry-pick after #18 |
| #18 | `a27f189` | authorized-source evidence and audit documentation | ancestor of #19 | integrate once; superseded by #19 |
| #19 | `46225fe` | authorized OHLCV file pipeline and rejection accounting | ancestor of #20 | integrate once; superseded by #20 |
| #20 | `8309d3b` | guarded SSI FastConnect adapter | ancestor of #21 | integrate once; superseded by #21 |
| #21 | `0173fc6` | guarded FiinGroup boundary and entitlement status | current chain tip | review as the single combined change |

The ancestry check shows each later head contains the earlier head. The chain
must therefore be reviewed and integrated as one linear series (or as one final
tip), never by merging all five heads independently. No PR is considered
production-ready solely because its code is present: CI, migration checks,
provider entitlement, and real-response acceptance remain separate gates.

## Data-source classification

- Securities bootstrap and CSV/XLSX imports: file-authorized, not full-market.
- Existing Yahoo rows: development-source observations with provenance; not a
  licensed commercial feed claim.
- SSI FastConnect SDK: implemented boundary, but `BLOCKED` until credentials,
  account approval and a successful authorized request are recorded.
- FiinGroup financials: commercial entitlement remains blocked until verified.

## Integration guardrails

1. Preserve the working tree and do not merge while unrelated uncommitted
   changes exist.
2. Validate the final chain with backend tests, Ruff, frontend build/lint and
   Alembic migration checks.
3. Require a real SSI acceptance artifact before changing the provider status
   from configured/blocked to live verified.

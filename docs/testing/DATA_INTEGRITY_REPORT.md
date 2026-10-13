# Data Integrity & Financial Validation Report

## Scope

Task 01 audits the persisted market-price and financial-statement paths. The
changes are on branch `codex/data-integrity-validation`, based on the merged
`main` revision `269f19f0690bde1be250d258e5eb58ead0e7a22` (PR #3).

This report deliberately does not claim that a live market-data or BCTC
provider is production-ready. Yahoo Finance remains a development connector;
FireAnt, SSI and FiinGroup are catalogued but are disabled until valid account,
scope and redistribution rights are supplied.

## Confirmed defects and root causes

| Area | Root cause | Remediation |
| --- | --- | --- |
| Price replay | Same-session rows were keyed by provider timestamp, so a corrected bar could coexist with the old bar and be counted as a second session. | Store `provider_id` and `market_session_date`; upsert one observation per provider/session and rank canonical sessions before calculating change. |
| Provider trust | Fixture/live observations were ranked only by timestamp. | Canonical selection uses configured provider priority, validation status and fixture/development trust metadata. |
| Incremental sync | An empty provider response was treated as an invalid series. | Incremental empty responses now complete successfully with zero writes and preserve the cursor. |
| Financial replay | Period identity omitted `statement_status`, and exact replays were reported as updates. | Migration 0014 separates original/amended periods; exact item replay is skipped. |
| Financial verification | Automated CSV import could preserve a provider's `verified` label. | Automated sync downgrades imported values to `unverified`; only an authorized human import can mark verified. |
| Financial validation | Balance equation, negative totals and missing fields were not persisted as a reviewable result. | Every touched period produces a validation report with checks, errors, warnings, source and timestamp; strict sync rolls back serious errors. |
| Formula scope | ROIC and leverage formulas were applied uniformly to banks and non-financial issuers. | ROIC uses NOPAT/average invested capital when inputs exist; bank/securities/insurance leverage and ROIC are null with an explanation. |
| Secure CSV retrieval | HTTPS alone did not prevent private-IP SSRF, oversized responses, unsafe redirects or unbounded retries. | Exact host allowlist, DNS public-IP checks, redirect validation, streaming byte cap and bounded retry policy are enforced. |

## Data provenance policy

Each persisted price carries source/provider, retrieval timestamp, market session
date, validation status and source mode. Financial periods/items carry source,
source URL, reporting period, scope, original/amended status, unit, currency,
verification status and update timestamp. No missing price is replaced by a
synthetic value.

The canonical price query chooses one trusted row per security and market
session before deriving the latest/previous change. Retrieval time is not used
as a substitute for the trading session date.

## Verification performed

### Baseline before the change

- Ruff: passed.
- Backend pytest: 57 passed, 1 warning.
- Frontend lint: passed.
- Frontend production build: passed.

### Current branch

- Backend Ruff: passed.
- Backend pytest: **63 passed, 1 warning**.
- SQLite Alembic upgrade → downgrade → upgrade: passed; head is `0014`.
- Frontend lint: passed.
- Frontend production build: passed (Next.js 16.4.0).
- `git diff --check`: passed before commit.

The tests cover same-session conflicting prices, replay idempotency, trusted
provider selection, original/amended financial versions, hand-calculated ROIC,
financial-entity formula guards and private-IP sync blocking.

### Not run / blocked by environment

- PostgreSQL upgrade/downgrade/re-upgrade: Docker is not installed in this
  environment, so no PostgreSQL container was available.
- `pip-audit`: the bundled runtime does not include the `pip_audit` module.
- `npm audit`: registry access is blocked in this environment; no audit result
  is asserted.
- Live provider calls: no authorized production token/entitlement was supplied.

## Source capability record

| Source | Documentation | Capability/status | Authentication and rights |
| --- | --- | --- | --- |
| Yahoo Finance chart | [Yahoo API terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) | Historical OHLCV connector, development-only; not an official exchange feed | No token; commercial/redistribution rights are not asserted |
| FireAnt REST API v1 | [api.fireant.vn](https://api.fireant.vn/) | Metadata and statements are catalogued, disabled until a real scoped call succeeds | OAuth2 bearer token and applicable data agreement |
| SSI FastConnect v3 | [SSI developer docs](https://developers.ssi.com.vn/docs/getting-started/overview) | Historical OHLCV/index capability catalogued, connector disabled | Registered API key/secret, approval and service terms |
| FiinGroup Datafeed | [FiinGroup datafeed](https://datafeed.fiingroup.vn/) | Full capability catalogued, disabled | Commercial credentials, contract and redistribution entitlement |
| Authorized user file | Internal CSV/XLSX import | Enabled for metadata, corporate actions and financial statements | Admin authentication plus operator confirmation of lawful use |

No undocumented endpoint or internal API is used. A provider is not marked
`COMPLETE` merely because credentials are configured; an authenticated request
and a valid response must be recorded first.

## Remaining limitations

- Exchange holiday/session calendars are not yet supplied by an authorized
  exchange feed; session dates are timezone-normalized and must still be
  reconciled against an official calendar when one is licensed.
- DNS is checked before each request, but a production deployment should also
  enforce egress policy at the network layer to cover DNS-rebinding races.
- Financial statement import validates structure and accounting equations but
  does not independently verify issuer disclosures.

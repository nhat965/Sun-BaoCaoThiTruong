# Task 05 — data platform audit

This repository reports data capability using two separate facts:

1. **Coverage** is the number of rows persisted in PostgreSQL (or the local
   development database).
2. **Verification** records whether a provider request, an authorized file
   import, or only a labelled fixture produced those rows.

The read-only endpoint `GET /api/v1/data-platform/capabilities` returns both
facts and uses the following status values:

| Status | Meaning |
| --- | --- |
| `IMPLEMENTED_AND_LIVE_VERIFIED` | An authorized provider request succeeded and its sync run is persisted. This does not grant redistribution rights. |
| `IMPLEMENTED_FILE_VERIFIED` | A supplied file was schema-validated and persisted. It is not realtime data. |
| `IMPLEMENTED_MOCK_TESTED` | Only a labelled fixture has been exercised. |
| `CONFIGURED_NOT_VERIFIED` | Configuration exists, but no successful authorized request is persisted. |
| `BLOCKED_EXTERNAL_DEPENDENCY` | Credentials, contract, source rights, or an official calendar are missing. |
| `NOT_IMPLEMENTED` | No persisted dataset or implementation evidence exists. |

## Current source matrix

| Dataset/capability | Code path | Current evidence | Production blocker |
| --- | --- | --- | --- |
| Securities metadata | `registry.py`, authorized securities import | Bootstrap registry and validated CSV/XLSX importer | Full-market master and redistribution rights must be supplied. |
| Historical OHLCV | `DataSyncService`, SSI guarded connector, authorized OHLCV CSV, development Yahoo connector | Fixture/import tests; a live label is emitted only after a persisted successful request | SSI contract/key and provider rights are not present in this environment. Yahoo is development-only until rights are verified. |
| VN-Index, VN30, HNX-Index, UPCoM-Index | `market_foundation.py`, authorized index importer | Schema/idempotency tests and persisted rows when imported | Official exchange/provider source and calendar entitlement. |
| Financial statements | `financial.py`, `FinancialRepository`, authorized BCTC CSV/XLSX path | Normalization, validation, and import tests | FiinGroup contract/endpoint/rights or lawful issuer export. |
| Corporate actions | `corporate_actions.py`, authorized importer | Validation/idempotency tests | Authorized provider or issuer/exchange source. |
| Market cap and actual trading value | Columns on `PriceObservation` | Counts only where provider supplies a value | Never inferred from close × volume; source must provide the field. |
| Foreign flow | No persisted provider/table | Explicitly unavailable | Authorized provider and schema are required. |

## Repository / PR audit

The GitHub PR metadata was checked against `nhat965/Sun-BaoCaoThiTruong` on
2026-10-15. PRs #17–#21 are open and unmerged; they form a stacked sequence,
not five independent changes to merge blindly:

| PR | Head | Base | Result |
| --- | --- | --- | --- |
| [#17](https://github.com/nhat965/Sun-BaoCaoThiTruong/pull/17) | `audit/market-data-production-readiness` | `main` | Open, not merged; production-readiness hardening and benchmark. |
| [#18](https://github.com/nhat965/Sun-BaoCaoThiTruong/pull/18) | `feature/authorized-market-data-acquisition` | PR #17 head | Open, not merged; source evidence and operator setup. |
| [#19](https://github.com/nhat965/Sun-BaoCaoThiTruong/pull/19) | `feature/authorized-market-data-acquisition-pr-b` | PR #18 head | Open, not merged; authorized OHLCV importer. |
| [#20](https://github.com/nhat965/Sun-BaoCaoThiTruong/pull/20) | `feature/authorized-market-data-acquisition-pr-c` | PR #19 head | Open, not merged; guarded SSI adapter. |
| [#21](https://github.com/nhat965/Sun-BaoCaoThiTruong/pull/21) | `feature/authorized-market-data-acquisition-pr-d` | PR #20 head | Open, not merged; guarded FiinGroup boundary. |

Local `main` remains at `d2b428d`; the current checkout contains the stacked
provider commits through `0173fc6` plus uncommitted PR-E/PR-F work. Nothing from
this Task 05 audit has been merged into `main`.

The API never calls a provider while producing this matrix. A configured
credential is not evidence of a successful call. Empty provider responses do
not delete historical rows.

`GET /api/v1/data-quality/reconciliation` and
`python scripts/data_reconciliation_report.py` provide the same read-only
reconciliation view for operations. `records_before` is intentionally `null`
when no external snapshot was supplied; the report therefore cannot be
misread as a comparison against market truth.

## Official provider references

- SSI FastConnect overview and authentication: <https://developers.ssi.com.vn/docs/getting-started/overview> and <https://developers.ssi.com.vn/docs/api-reference/auth-token>.
- SSI Python service classes: <https://developers.ssi.com.vn/docs/sdk/python/service-classes>.
- FiinGroup BCTC API and original reports: <https://datafeed.fiingroup.vn/api-doanh-nghiep/bao-cao-tai-chinh-bctc> and <https://datafeed.fiingroup.vn/api-doanh-nghiep/bao-cao-tai-chinh-bctc/file-bctc-goc/tai-lieu-goc-bao-cao-tai-chinh>.

The SSI contract surface reviewed for the guarded adapter is the documented
Python service layer: `get_securities_info_by_board()`,
`get_securities_info_by_index()`, `get_securities_info()`,
`data.market_data.get_ohlc_1day_historical(...)`, `get_indexes()`,
`get_indexes_by_board()`, `get_index_summary()`,
`get_index_summary_historical()`, `get_board_summary()`,
`get_board_summary_historical()`, `get_securities_summary()`,
`get_securities_summary_historical()`, and
`get_securities_summary_by_index()`. The repository does not enable an
undocumented URL when an operator has not supplied a contract-approved endpoint
template.

The connector layer intentionally does not invent undocumented endpoints. The
operator must supply endpoint/entitlement configuration and run the live
acceptance checks before a capability can become `IMPLEMENTED_AND_LIVE_VERIFIED`.

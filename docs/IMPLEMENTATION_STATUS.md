# V4.1 implementation status

| Capability | Status | Evidence / remaining gap |
|---|---|---|
| Existing MVP flow | DONE | Search → prices → analysis → chart → news metadata → PDF retained. |
| Securities master | PARTIAL | Database registry, Vietnamese aliases, provider IDs and authorized CSV/XLSX incremental import implemented; bundled bootstrap is not full-market coverage. |
| Securities Explorer | DONE | Server-side search/filter/sort/pagination, facets, nullable price/fundamental fields, responsive table/cards, local pinning and analysis navigation verified. |
| Market data foundation (PR-A) | PARTIAL | Additive migration `0017`, canonical provider/session deduplication, Vietnam timezone/weekend semantics, index provenance API/import and history-depth coverage diagnostics implemented. Authorized index feed, official holiday calendar, market cap and foreign-flow data remain blocked. |
| Market breadth & trend (PR-B) | PARTIAL | Advance/Decline, MA20/50/200 breadth, 20-session extremes, historical points, conservative regime classification and persisted snapshots are implemented; coverage is partial and no calibrated probability or authorized index divergence is available. |
| Sector & liquidity intelligence (PR-C) | PARTIAL | Taxonomy-aware sector ranking/drilldown, multi-horizon performance, relative volume, concentration and explicit actual-value/foreign-flow gaps are implemented with migration `0019`; authorized VN-Index, trading-value and foreign-flow feeds remain unavailable. |
| Source provenance | DONE | Price records include source, URL, retrieval/market timestamps, freshness, validation and adjustment policy. |
| OHLCV normalization/storage | DONE | Sort, deduplicate, reject invalid bars, initial/incremental cursors and idempotent upsert implemented; live HPG/FPT repeat-sync verified. |
| Provider orchestration | PARTIAL | Explicit seven-capability matrix, priority/failover loop, process-local circuit breaker and persisted sync runs/errors implemented; only Yahoo price provider currently operational. |
| FireAnt | BLOCKED | Status connector implemented; real data requires a user token plus verified scopes/entitlements. |
| VPS SmartOne | BLOCKED | No verified official read-only portfolio API/credentials supplied. |
| API write protection | DONE | Bearer admin token, reader/admin separation, rate limiting, audit logs and 401/403/422 tests. |
| Circuit breaker | DONE | Shared registry across manager instances, threshold/cooldown/half-open recovery and source health persistence. |
| Financial statement storage | PARTIAL | Validated authorized CSV pipeline, raw/normalized units, source/scope/verification metadata and protected upserts through migration `0013`; automatic financial sync is truthfully `BLOCKED` without an entitled provider. |
| Financial ratios | DONE | Stored-period metrics include growth, average-balance ROE/ROA, ROIC, margins, EPS/BVPS, leverage, cash flow and safe valuation multiples. |
| Relative valuation | PARTIAL | Explicit P/E + P/B scenarios plus user-assumption DCF and sensitivity matrix; no verified peers or historical bands. |
| Technical analysis V2 | DONE | Expanded indicators, four component scores, conflict detection and formula documentation. |
| Fundamentals | PARTIAL | Deterministic safe calculator implemented; no licensed financial-statement connector or sector benchmark. |
| News intelligence | PARTIAL | Configurable metadata-only RSS connectors, normalized storage, URL/title deduplication, event groups, relevance and evidence; licensed publisher feeds remain unconfigured. |
| Research scenarios | PARTIAL | Bull/base/bear conditions and two-sided factors shown; no target price without valuation inputs. |
| Frontend hardening | DONE | Registry search, score hierarchy, conflicts, scenarios, normalized BCTC ledger, pipeline state, data-quality coverage and responsive layout. |
| Typed analyst tools | DONE | Closed tool registry, deterministic question planning and explicit unavailable-tool limitations; no arbitrary model-selected function execution. |
| Market overview/reports | PARTIAL | Breadth, volume, estimated value, sector performance and idempotent pre/post-market snapshots are persisted; licensed index/foreign-flow feeds and production scheduler remain unavailable. |
| Social classification | PARTIAL | Authorized submitted content receives deterministic sentiment/type/uncertainty labels; no platform scraping or live social feed. |
| Portfolio ledger | PARTIAL | Manual/API and idempotent CSV transactions, average cost, realized/unrealized P&L and concentration are implemented; VPS remains blocked. |
| Persistent job/cache scheduler | PARTIAL | Leased EOD jobs, heartbeats, exponential retry, snapshots, watchlists and alert-rule persistence are implemented; production scheduler/worker is not deployed. |
| Auth/RBAC/audit security | DONE | Bearer admin/reader separation, fail-closed writes, fixed-window rate limit, trusted hosts, docs gating and audit logs. |
| Dark mode | NOT STARTED | Current design remains light-only. |
| Docker verification | BLOCKED | Docker engine was unavailable in the execution environment. |

## V4 milestone status

| Milestone | Status | Evidence / remaining gap |
|---|---|---|
| M1 Security and reliability | COMPLETE | Structured metric-specific AI claims, tokenized job leases/heartbeats, stale-worker protection, streamed-body limits, authorization and rate-limit regressions pass. Shared rate-limit backend remains for multi-worker deployment. |
| M2 Reliable Vietnamese financial data | PARTIAL | Authorized file ingestion, provider capability matrix, persisted initial/incremental sync audit, raw/normalized financial units and live HPG/FPT Yahoo verification are traceable. Full-market synchronization, official calendar and licensed automatic BCTC provider remain blocked. |
| M3 Fundamental research and valuation | PARTIAL | Deterministic metrics, like-for-like quarterly/yearly comparisons, statement scope/amendment metadata, trends, relative valuation, explicit DCF and sensitivity matrix are implemented. Verified peer/sector datasets and historical multiple bands remain unavailable. |
| M4 News and event intelligence | PARTIAL | Configurable RSS metadata pipeline, event storage, deduplication and source/category/time filtering are implemented. More than one genuinely live authorized feed is not configured. |
| M5 AI analyst and verification | PARTIAL | Typed claims and a closed typed tool plan verify metric/value/unit/period/symbol/evidence/forecast support; production LLM evaluation remains credential-dependent. |
| M6 Market overview and daily reporting | PARTIAL | Stored-data breadth/sector aggregation, explicit missing index/foreign-flow fields, idempotent pre/post reports and leased EOD snapshots are implemented; production delivery and official calendar remain. |
| M7 Social and portfolio | PARTIAL | Deterministic classification and manual/CSV portfolio accounting are implemented without scraping or trading access; live social and VPS APIs remain blocked. |
| M8 Release readiness | PARTIAL | Local lint, 55 tests, frontend build and migration cycle through `0013` pass. PostgreSQL CI, dependency audit and health-gated Compose are configured; Docker smoke cannot run on this host. |

Statuses are evidence-based: `COMPLETE` means implemented and locally verified, `PARTIAL` means a useful vertical slice exists with an explicit gap, and `BLOCKED` requires credentials, rights or infrastructure not provided here.
## PR-D — Risk & Scenario Engine

- Added evidence-first risk signals and conditional positive/base/negative scenarios.
- Added persisted, idempotent snapshots and `/api/v1/market/risks` plus `/api/v1/market/scenarios`.
- No uncalibrated probabilities or price targets; data limitations are explicit.

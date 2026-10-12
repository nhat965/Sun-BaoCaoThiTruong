# V3 implementation status

| Capability | Status | Evidence / remaining gap |
|---|---|---|
| Existing MVP flow | DONE | Search → prices → analysis → chart → news metadata → PDF retained. |
| Securities master | PARTIAL | Database registry, Vietnamese aliases and authorized CSV import implemented; bundled 13-symbol bootstrap is not full-market coverage. |
| Source provenance | DONE | Price records include source, URL, retrieval/market timestamps, freshness, validation and adjustment policy. |
| OHLCV normalization/storage | DONE | Sort, deduplicate, reject invalid bars and incremental upsert implemented. |
| Provider orchestration | PARTIAL | Priority/failover loop and process-local circuit breaker implemented; only Yahoo price provider currently operational. |
| FireAnt | BLOCKED | Status connector implemented; real data requires a user token plus verified scopes/entitlements. |
| VPS SmartOne | BLOCKED | No verified official read-only portfolio API/credentials supplied. |
| API write protection | DONE | Bearer admin token, reader/admin separation, rate limiting, audit logs and 401/403/422 tests. |
| Circuit breaker | DONE | Shared registry across manager instances, threshold/cooldown/half-open recovery and source health persistence. |
| Financial statement storage | PARTIAL | Validated authorized CSV pipeline and migrations `0004`; no licensed live financial provider yet. |
| Financial ratios | DONE | Stored-period metrics include growth, average-balance ROE/ROA, ROIC, margins, EPS/BVPS, leverage, cash flow and safe valuation multiples. |
| Relative valuation | PARTIAL | Explicit P/E + P/B bull/base/bear calculator; no verified peers, historical bands or DCF yet. |
| Technical analysis V2 | DONE | Expanded indicators, four component scores, conflict detection and formula documentation. |
| Fundamentals | PARTIAL | Deterministic safe calculator implemented; no licensed financial-statement connector or sector benchmark. |
| News intelligence | PARTIAL | Configurable metadata-only RSS connectors, normalized storage, URL/title deduplication, event groups, relevance and evidence; licensed publisher feeds remain unconfigured. |
| Research scenarios | PARTIAL | Bull/base/bear conditions and two-sided factors shown; no target price without valuation inputs. |
| Frontend hardening | DONE | Registry search, score hierarchy, conflicts, scenarios, stored-fundamentals panel and responsive layout. |
| Persistent job/cache scheduler | PARTIAL | Idempotent EOD jobs, retry state, job runs, watchlists and alert-rule persistence are implemented; production scheduler/worker is not deployed. |
| Auth/RBAC/audit security | DONE | Bearer admin/reader separation, fail-closed writes, fixed-window rate limit, trusted hosts, docs gating and audit logs. |
| Dark mode | NOT STARTED | Current design remains light-only. |
| Docker verification | BLOCKED | Docker engine was unavailable in the execution environment. |

## V4 milestone status

| Milestone | Status | Evidence / remaining gap |
|---|---|---|
| M1 Security and reliability | COMPLETE | Protected valuation persistence, atomic job claiming/retry recovery, request/LLM limits, production config validation; 21 backend tests pass. Shared rate-limit backend remains for multi-worker deployment. |
| M2 Reliable Vietnamese financial data | PARTIAL | Authorized securities CSV and Yahoo development connector are traceable; full-market synchronization and licensed providers are not configured. |
| M3 Fundamental research and valuation | PARTIAL | Deterministic stored-period metrics and relative valuation exist; trends, peers, historical bands and DCF remain. |
| M4 News and event intelligence | PARTIAL | Configurable RSS metadata pipeline and event storage exist; more than one genuinely live authorized feed is not configured. |
| M5 AI analyst and verification | PARTIAL | Typed evidence response, optional provider, limits and audit exist; numeric claim/citation validation remains. |
| M6 Social sentiment | NOT STARTED | No authorized discussion dataset supplied. |
| M7 Daily reporting | PARTIAL | Persistent jobs and report endpoint exist; production scheduler, trading calendar and delivery channels remain. |
| M8 Portfolio/VPS | NOT STARTED | Manual portfolio workflows are not implemented; VPS remains blocked pending official API. |
| M9 Release readiness | PARTIAL | Local lint/tests/build/migrations pass; CI, Docker smoke and dependency scan remain. |

Statuses are evidence-based: `COMPLETE` means implemented and locally verified, `PARTIAL` means a useful vertical slice exists with an explicit gap, and `BLOCKED` requires credentials, rights or infrastructure not provided here.

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
| News intelligence | PARTIAL | Vietnamese alias matching, relevance, deduplication and event categories; one RSS source, no full sentiment/event pipeline. |
| Research scenarios | PARTIAL | Bull/base/bear conditions and two-sided factors shown; no target price without valuation inputs. |
| Frontend hardening | DONE | Registry search, score hierarchy, conflicts, scenarios, stored-fundamentals panel and responsive layout. |
| Persistent job/cache scheduler | NOT STARTED | Requests are synchronous; no distributed queue/cache scheduler. |
| Auth/RBAC/audit security | NOT STARTED | Local MVP has no user accounts or admin boundary. |
| Dark mode | NOT STARTED | Current design remains light-only. |
| Docker verification | BLOCKED | Docker engine was unavailable in the execution environment. |

Statuses are evidence-based: `DONE` means implemented and locally verified, `PARTIAL` means a useful vertical slice exists with an explicit gap, and `BLOCKED` requires credentials, rights or infrastructure not provided here.

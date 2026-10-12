# V2 implementation status

| Capability | Status | Evidence / remaining gap |
|---|---|---|
| Existing MVP flow | DONE | Search → prices → analysis → chart → news metadata → PDF retained. |
| Securities master | PARTIAL | Database registry, Vietnamese aliases and authorized CSV import implemented; bundled 13-symbol bootstrap is not full-market coverage. |
| Source provenance | DONE | Price records include source, URL, retrieval/market timestamps, freshness, validation and adjustment policy. |
| OHLCV normalization/storage | DONE | Sort, deduplicate, reject invalid bars and incremental upsert implemented. |
| Provider orchestration | PARTIAL | Priority/failover loop and process-local circuit breaker implemented; only Yahoo price provider currently operational. |
| FireAnt | BLOCKED | Status connector implemented; real data requires a user token plus verified scopes/entitlements. |
| VPS SmartOne | BLOCKED | No verified official read-only portfolio API/credentials supplied. |
| Technical analysis V2 | DONE | Expanded indicators, four component scores, conflict detection and formula documentation. |
| Fundamentals | PARTIAL | Deterministic safe calculator implemented; no licensed financial-statement connector or sector benchmark. |
| News intelligence | PARTIAL | Vietnamese alias matching, relevance, deduplication and event categories; one RSS source, no full sentiment/event pipeline. |
| Research scenarios | PARTIAL | Bull/base/bear conditions and two-sided factors shown; no target price without valuation inputs. |
| Frontend hardening | DONE | Registry search, score hierarchy, conflicts, scenarios and responsive layout. |
| Persistent job/cache scheduler | NOT STARTED | Requests are synchronous; no distributed queue/cache scheduler. |
| Auth/RBAC/audit security | NOT STARTED | Local MVP has no user accounts or admin boundary. |
| Dark mode | NOT STARTED | Current design remains light-only. |
| Docker verification | BLOCKED | Docker engine was unavailable in the execution environment. |

Statuses are evidence-based: `DONE` means implemented and locally verified, `PARTIAL` means a useful vertical slice exists with an explicit gap, and `BLOCKED` requires credentials, rights or infrastructure not provided here.

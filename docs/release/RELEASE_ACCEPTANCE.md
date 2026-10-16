# PR-F — End-to-end acceptance and release gate

PR-F turns the existing tests and CI checks into an explicit release gate. A release is
not labelled live or production-ready merely because the scheduler process starts.

## Acceptance matrix

| Area | Evidence | Gate |
|---|---|---|
| Registry | `tests/test_release_acceptance.py` verifies the seeded 13-row fixture | PASS for fixture; full-market coverage remains PARTIAL |
| OHLCV | Fixture HPG sync, replay and provenance assertions | PASS for fixture; live requires an authorized provider |
| Financial statements | Provider catalog and blocked sync status | BLOCKED until credential, entitlement and a successful authorized call |
| Scheduler | Worker fixture run, dependency gate, lease/idempotency tests | PASS for fixture; production schedule requires Docker/PostgreSQL runtime |
| PostgreSQL | `scripts/verify_postgres_acceptance.py` races two lease claimers on the CI PostgreSQL service | CI gate |
| Docker | `docker compose config --quiet`; runtime smoke must be run on a host with Docker | Config gate; runtime is environment-dependent |
| Frontend | lint/build and `/admin` route generation | PASS |
| Dependency audit | `pip-audit` and `npm audit --omit=dev` in CI | CI gate |

## Source truthfulness

Fixture rows are labelled `fixture`; authorized files retain their source and verification
state; Yahoo remains a development/delayed connector. SSI, FireAnt, FiinGroup, official
index feeds, market cap, foreign flow and full-market securities master remain blocked when
credentials, rights or contracts are absent. Scheduler retries and automates only a
capability that the provider catalog marks usable; it cannot create missing entitlements.

## Release decision

Promote only when CI is green, PostgreSQL acceptance passes, the Docker runtime smoke is
green in the target environment, and an operator has reviewed `GET /api/v1/data-quality/coverage`.
If a source is blocked, release may be a development/partial-data deployment only and must
retain the limitations above.

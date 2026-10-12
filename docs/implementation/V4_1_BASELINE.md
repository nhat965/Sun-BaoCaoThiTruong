# V4.1 implementation baseline

Recorded: 2026-10-12  
Baseline: `origin/main` at `10aa005`  
Implementation branch: `feature/v4.1-data-intelligence`

## Verified baseline

- Backend lint: passed (`ruff check app tests`).
- Backend tests: 24 passed; one upstream Starlette `TestClient`/httpx deprecation warning.
- Frontend lint: passed.
- Frontend production build: passed.
- Database models and migrations are present through Alembic revision `0008`.
- Docker and the `psql` client are not installed on this host, so PostgreSQL/container acceptance cannot be executed locally. SQLite remains the local automated-test database.

## Audit findings against V4.1

### P0 gaps

1. AI output is free-form prose checked by scanning for numbers and citation tokens. It does not bind a claim to a symbol, metric, unit, period, evidence record, or forecast policy.
2. Automation claims jobs with status and timestamp only. A worker that lost ownership can still update the newest run and overwrite the result of a newer worker.
3. The global request limit trusts `Content-Length`; a streamed or chunked body can bypass it.

### Data and product constraints

- Fixture and delayed-development connectors are explicitly labelled; they are not represented as licensed real-time production feeds.
- FireAnt access is capability-gated and remains unavailable without an authorized token and entitlement.
- A second authorized news provider, licensed peer/sector history, production LLM evaluation credentials, Redis/shared rate limiting, and deployment infrastructure are not available in this environment.
- These external dependencies must remain reported as `PARTIAL` or `BLOCKED`; they will not be replaced with fabricated data or fabricated credentials.

## Execution order

1. Typed claim contract, deterministic claim verification, and verified narrative rendering.
2. Tokenized job ownership, leases, heartbeats, exact run identity, and stale-worker protection.
3. Streaming request-body enforcement plus regression/security tests and proxy guidance.
4. Continue M2–M8 using only authorized capabilities, with explicit availability and provenance.

# Scheduler acceptance evidence

Automated evidence on PR-E:

* The current backend suite has 119 passing tests (including scheduler/release acceptance; slot idempotency, two-claimer
  lease ownership, fixture coverage and unavailable foreign flow) pass.
* Ruff passes for `app`, `scripts` and scheduler tests.
* Alembic `upgrade head → downgrade base → upgrade head` passes against SQLite for
  migration `0021_scheduler_job_metadata`.
* Idempotency is enforced by the unique `jobs.idempotency_key`; concurrent claims are
  guarded by the existing atomic update and lease token.
* A fixture worker run processed 13 OHLCV jobs with `status=SUCCESS` and `source_freshness=fixture`,
  marked securities-master/index/financial jobs `BLOCKED`, then processed analytics and report
  only in subsequent cycles after dependency gates were terminal. A second replay reused the
  same 31 idempotency keys.

The suite is fixture/development evidence, not live-market acceptance. PostgreSQL locking,
licensed SSI/FiinGroup calls, official holiday calendars, and Docker runtime are not
claimed here unless the CI environment supplies them. The CI workflow remains the source
of truth for the PostgreSQL service and frontend gates.

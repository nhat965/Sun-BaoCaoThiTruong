# Production scheduler architecture

PR-E extends the existing leased `jobs`/`job_runs` kernel; it does not start a second
scheduler in FastAPI. `apps/api/scripts/run_scheduler.py` is the only worker entrypoint.

## Flow

`Securities → OHLCV / indices → validation → market analytics → daily report` and
`Authorized financial provider/file → validation → financial metrics → research`.

`ProductionScheduler.enqueue_due()` creates an idempotency key per job, local date and
configured slot. `run_pending()` uses the database atomic claim, lease heartbeat and
bounded concurrency from `SCHEDULER_MAX_CONCURRENCY`. A blocked provider is terminal for
that run and is not retried in a loop. Failed/timeouts use the existing exponential
backoff. Report jobs refuse to create a snapshot when upstream market coverage is
unavailable; partial coverage remains explicitly labelled in report limitations.

## Configuration

`SCHEDULER_ENABLED` defaults to `false`; `SCHEDULER_DAILY_TIMES` is a comma-separated list
of `HH:MM` values in `MARKET_TIMEZONE` (default `Asia/Ho_Chi_Minh`). `--once` is an
explicit operator action and works even when the long-running worker is disabled.

## Isolation and security

The worker has no frontend token and does not log credentials. Docker Compose runs it as a
separate service. Provider selection still goes through the capability/entitlement matrix;
fixture mode is never selected implicitly in production.

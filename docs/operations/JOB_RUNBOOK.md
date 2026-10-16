# Scheduler job runbook

Start the worker after migrations:

```bash
cd apps/api
python scripts/run_scheduler.py
python scripts/run_scheduler.py --once
# Developer-only SQLite bootstrap; production runs Alembic from the API image first.
python scripts/run_scheduler.py --once --init-db
```

Compose operators can use `docker compose up -d worker`, `docker compose logs -f worker`,
and `docker compose restart worker`. The worker handles SIGTERM between polling cycles.

Supported jobs are `SYNC_SECURITIES_MASTER`, `SYNC_OHLCV`, `SYNC_MARKET_INDICES`,
`SYNC_FINANCIAL_STATEMENTS`, `RECALCULATE_MARKET_INTELLIGENCE`, `GENERATE_DAILY_REPORT`,
and `CHECK_PROVIDER_HEALTH`. Securities-master/index jobs become `BLOCKED` until an
authorized provider is configured; they do not fabricate rows.

Admin endpoints require `Authorization: Bearer $ADMIN_API_TOKEN`:

* `GET /api/v1/admin/operations`
* `POST /api/v1/admin/scheduler/run-once`
* `POST /api/v1/admin/providers/health-check`
* `POST /api/v1/admin/jobs/{id}/retry`
* `POST /api/v1/admin/data/sync/{symbol}`

Retry is explicit and only accepts `FAILED`, `BLOCKED` or `RETRY_PENDING`. A duplicate
enqueue returns the existing idempotent job rather than creating another execution.

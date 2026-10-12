# Automation architecture

Jobs are persisted with a unique `(job_type, symbol, scheduled_for)` idempotency key. A worker claims a queued/retry-pending job with an atomic SQL `UPDATE ... WHERE status ...`, so concurrent workers cannot both execute the same job. A stale `RUNNING` row can be reclaimed after the configured timeout. Attempts are bounded and failures become `RETRY_PENDING` or `FAILED`.

The API currently exposes enqueue/list/run endpoints. A production scheduler/worker, trading-calendar integration and notification delivery are intentionally separate deployment work and must not be inferred from the local API.

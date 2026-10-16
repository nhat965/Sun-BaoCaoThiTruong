# Deployment runbook

## PostgreSQL 16 options

Docker Compose is the reproducible path:

```bash
docker compose up -d db
docker compose run --rm api alembic upgrade head
```

For a native PostgreSQL 16 installation, create an isolated database and point
the API at it before running the same migration command:

```bash
createuser --createdb market
createdb -O market market_intelligence
set DATABASE_URL=postgresql+psycopg://market:<password>@localhost:5432/market_intelligence
cd apps/api
alembic upgrade head
```

Verify the target before calling the application data endpoints:

```bash
psql "$DATABASE_URL" -c "select version();"
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/data-quality/coverage
```

Do not report PostgreSQL as PASS unless `psql`/the container connection,
migrations, and at least one ingest/replay check have succeeded against that
database. The current workstation has neither a listening local PostgreSQL
service nor Docker, so its PostgreSQL status remains **BLOCKED**.

1. Provide a PostgreSQL URL and run migrations from the API image:

   ```bash
   docker compose run --rm api alembic upgrade head
   ```

2. Configure `MARKET_TIMEZONE`, scheduler times and only provider credentials/rights that
   have been approved. Keep `MARKET_DATA_MODE=live` in production; fixture mode is for
   acceptance/demo only.

3. Start the stack and inspect health:

   ```bash
   docker compose up -d --build
   docker compose ps
   docker compose logs --tail=100 api worker web
   curl http://localhost:8000/api/v1/health
   curl http://localhost:8000/api/v1/data-quality/coverage
   ```

   The worker depends on the API health check so Alembic has completed before it claims a
   job. It does not call `create_all` in production.

4. Stop safely with `docker compose down`; keep the database volume unless a data-retention
   procedure explicitly says otherwise. A worker restart is safe because leases expire and
   idempotency keys prevent duplicate scheduling.

5. If an operation is blocked, inspect `/api/v1/providers` and `/api/v1/admin/operations`.
   Configure the missing entitlement, then use the explicit admin retry endpoint. Do not
   mark the source live based on a configured token alone.

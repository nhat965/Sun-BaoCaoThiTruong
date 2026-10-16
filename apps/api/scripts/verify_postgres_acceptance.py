"""Verify real PostgreSQL lease/idempotency behavior without touching market data.

The script creates one short-lived scheduler job, races two workers against it, and
removes only that probe row. It must receive a PostgreSQL URL; SQLite is rejected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(database_url: str) -> dict[str, object]:
    if not database_url.startswith("postgresql"):
        raise ValueError("PostgreSQL URL is required; SQLite is not an acceptable substitute.")
    os.environ["DATABASE_URL"] = database_url
    from sqlalchemy import delete, select, text

    from app.automation import AutomationService
    from app.database import JobRecord, JobRunRecord, SessionLocal

    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    service = AutomationService(None, max_retries=3, lease_seconds=60)
    key = f"release-acceptance:{uuid.uuid4().hex}"
    job = service.enqueue_job(
        "CHECK_PROVIDER_HEALTH", scheduled_for=datetime.now(UTC),
        idempotency_key=key, scope="market",
    )

    def claim(worker: str):
        return service.claim(job.id, worker_id=worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, ("postgres-worker-a", "postgres-worker-b")))
    owned = sum(lease is not None for lease in leases)
    try:
        if owned != 1:
            raise AssertionError(f"expected exactly one PostgreSQL lease owner, got {owned}")
        with SessionLocal() as session:
            rows = session.scalars(select(JobRecord).where(JobRecord.idempotency_key == key)).all()
            if len(rows) != 1:
                raise AssertionError(f"expected one idempotent job row, got {len(rows)}")
    finally:
        with SessionLocal() as session:
            session.execute(delete(JobRunRecord).where(JobRunRecord.job_id == job.id))
            session.execute(delete(JobRecord).where(JobRecord.id == job.id))
            session.commit()
    return {"status": "pass", "database": "postgresql", "lease_owners": owned, "idempotency_rows": 1}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        print(json.dumps({"status": "blocked", "reason": "DATABASE_URL is not configured"}))
        return
    try:
        print(json.dumps(run(args.database_url)))
    except Exception as exc:  # pragma: no cover - infrastructure diagnostics
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

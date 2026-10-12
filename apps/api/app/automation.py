"""Small idempotent automation kernel; a scheduler may trigger it in production."""
import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app.database import (
    AlertRuleRecord,
    JobRecord,
    JobRunRecord,
    SessionLocal,
    WatchlistItemRecord,
    WatchlistRecord,
)


@dataclass(frozen=True)
class JobLease:
    job_id: int
    symbol: str
    run_id: str
    claim_token: str
    worker_id: str
    lease_expires_at: datetime


class AutomationService:
    def __init__(
        self, analysis_service, max_retries: int = 3, lease_seconds: int = 1800
    ):
        self.analysis_service, self.max_retries = analysis_service, max_retries
        self.lease_seconds = lease_seconds

    def enqueue_eod(self, symbol: str, scheduled_for: datetime | None = None) -> JobRecord:
        scheduled = (scheduled_for or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
        with SessionLocal() as session:
            job = session.scalar(select(JobRecord).where(JobRecord.job_type == "eod", JobRecord.symbol == symbol.upper(), JobRecord.scheduled_for == scheduled))
            if job is None:
                now = datetime.now(UTC)
                job = JobRecord(job_type="eod", symbol=symbol.upper(), scheduled_for=scheduled, status="QUEUED", attempts=0, created_at=now, updated_at=now)
                session.add(job)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    job = session.scalar(select(JobRecord).where(JobRecord.job_type == "eod", JobRecord.symbol == symbol.upper(), JobRecord.scheduled_for == scheduled))
                if job is not None:
                    session.refresh(job)
            return job

    def claim(
        self, job_id: int, *, worker_id: str | None = None, now: datetime | None = None
    ) -> JobLease | None:
        """Atomically acquire a job and create an exact, immutable run identity."""
        now = now or datetime.now(UTC)
        worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        claim_token = uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        with SessionLocal() as session:
            claim = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.attempts < self.max_retries,
                    or_(
                        JobRecord.status.in_(["QUEUED", "RETRY_PENDING"]),
                        (JobRecord.status == "RUNNING")
                        & or_(
                            JobRecord.lease_expires_at.is_(None),
                            JobRecord.lease_expires_at <= now,
                        ),
                    ),
                )
                .values(
                    status="RUNNING",
                    attempts=JobRecord.attempts + 1,
                    updated_at=now,
                    claim_token=claim_token,
                    run_id=run_id,
                    claimed_at=now,
                    lease_expires_at=lease_expires_at,
                    worker_id=worker_id,
                    heartbeat_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if claim.rowcount != 1:
                job = session.get(JobRecord, job_id)
                if job is None:
                    raise LookupError("Job không tồn tại")
                return None
            session.execute(
                update(JobRunRecord)
                .where(
                    JobRunRecord.job_id == job_id,
                    JobRunRecord.status == "RUNNING",
                )
                .values(status="EXPIRED", finished_at=now, error="Lease expired and reclaimed")
                .execution_options(synchronize_session=False)
            )
            job = session.get(JobRecord, job_id)
            run = JobRunRecord(
                job_id=job.id,
                run_id=run_id,
                claim_token=claim_token,
                worker_id=worker_id,
                status="RUNNING",
                started_at=now,
                heartbeat_at=now,
                lease_expires_at=lease_expires_at,
            )
            session.add(run)
            session.commit()
            return JobLease(
                job_id=job.id,
                symbol=job.symbol,
                run_id=run_id,
                claim_token=claim_token,
                worker_id=worker_id,
                lease_expires_at=lease_expires_at,
            )

    def heartbeat(self, lease: JobLease, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        new_expiry = now + timedelta(seconds=self.lease_seconds)
        with SessionLocal() as session:
            owned = session.execute(
                update(JobRecord)
                .where(*self._ownership_filters(lease, now))
                .values(heartbeat_at=now, lease_expires_at=new_expiry, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            if owned.rowcount != 1:
                session.rollback()
                return False
            session.execute(
                update(JobRunRecord)
                .where(
                    JobRunRecord.run_id == lease.run_id,
                    JobRunRecord.claim_token == lease.claim_token,
                    JobRunRecord.status == "RUNNING",
                )
                .values(heartbeat_at=now, lease_expires_at=new_expiry)
                .execution_options(synchronize_session=False)
            )
            session.commit()
            return True

    async def run(self, job_id: int, *, worker_id: str | None = None) -> JobRecord:
        lease = self.claim(job_id, worker_id=worker_id)
        if lease is None:
            with SessionLocal() as session:
                job = session.get(JobRecord, job_id)
                if job is None:
                    raise LookupError("Job không tồn tại")
                session.expunge(job)
                return job
        try:
            result = await self.analysis_service.analyze(lease.symbol)
            return self.complete_success(
                lease, {"evidence_count": result.evidence_count}
            )
        except Exception as exc:  # noqa: BLE001 - failed jobs must be persisted for retry
            return self.complete_failure(lease, str(exc))

    def complete_success(
        self,
        lease: JobLease,
        result: dict[str, object],
        *,
        now: datetime | None = None,
    ) -> JobRecord:
        return self._complete(lease, result=result, error=None, now=now)

    def complete_failure(
        self, lease: JobLease, error: str, *, now: datetime | None = None
    ) -> JobRecord:
        return self._complete(lease, result=None, error=error[:1024], now=now)

    def _complete(
        self,
        lease: JobLease,
        *,
        result: dict[str, object] | None,
        error: str | None,
        now: datetime | None,
    ) -> JobRecord:
        now = now or datetime.now(UTC)
        with SessionLocal() as session:
            current = session.get(JobRecord, lease.job_id)
            if current is None:
                raise LookupError("Job không tồn tại")
            status = (
                "SUCCESS"
                if error is None
                else ("FAILED" if current.attempts >= self.max_retries else "RETRY_PENDING")
            )
            owned = session.execute(
                update(JobRecord)
                .where(*self._ownership_filters(lease, now))
                .values(
                    status=status,
                    last_error=error,
                    updated_at=now,
                    claim_token=None,
                    run_id=None,
                    lease_expires_at=None,
                    worker_id=None,
                    heartbeat_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if owned.rowcount == 1:
                session.execute(
                    update(JobRunRecord)
                    .where(
                        JobRunRecord.run_id == lease.run_id,
                        JobRunRecord.claim_token == lease.claim_token,
                        JobRunRecord.status == "RUNNING",
                    )
                    .values(
                        status=status,
                        finished_at=now,
                        error=error,
                        result_json=json.dumps(result or {}, ensure_ascii=False),
                        heartbeat_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
            else:
                session.execute(
                    update(JobRunRecord)
                    .where(
                        JobRunRecord.run_id == lease.run_id,
                        JobRunRecord.claim_token == lease.claim_token,
                        JobRunRecord.status == "RUNNING",
                    )
                    .values(
                        status="STALE",
                        finished_at=now,
                        error="Worker no longer owns a valid lease",
                    )
                    .execution_options(synchronize_session=False)
                )
            session.commit()
            job = session.get(JobRecord, lease.job_id)
            session.refresh(job)
            session.expunge(job)
            return job

    @staticmethod
    def _ownership_filters(lease: JobLease, now: datetime):
        return (
            JobRecord.id == lease.job_id,
            JobRecord.status == "RUNNING",
            JobRecord.run_id == lease.run_id,
            JobRecord.claim_token == lease.claim_token,
            JobRecord.worker_id == lease.worker_id,
            JobRecord.lease_expires_at > now,
        )

def job_schema(job: JobRecord) -> dict:
    return {"id": job.id, "job_type": job.job_type, "symbol": job.symbol, "scheduled_for": job.scheduled_for, "status": job.status, "attempts": job.attempts, "last_error": job.last_error}

def create_watchlist(name: str):
    with SessionLocal() as session:
        row = WatchlistRecord(name=name.strip(), created_at=datetime.now(UTC)); session.add(row); session.commit(); session.refresh(row); return row

def add_watchlist_item(watchlist_id: int, symbol: str):
    with SessionLocal() as session:
        if session.get(WatchlistRecord, watchlist_id) is None: raise LookupError("Watchlist không tồn tại")
        existing = session.scalar(select(WatchlistItemRecord).where(WatchlistItemRecord.watchlist_id == watchlist_id, WatchlistItemRecord.symbol == symbol.upper()))
        if existing is None:
            existing = WatchlistItemRecord(watchlist_id=watchlist_id, symbol=symbol.upper(), added_at=datetime.now(UTC)); session.add(existing); session.commit()
        return existing

def create_alert_rule(watchlist_id: int, rule_type: str, threshold: float | None):
    with SessionLocal() as session:
        if session.get(WatchlistRecord, watchlist_id) is None: raise LookupError("Watchlist không tồn tại")
        row = AlertRuleRecord(watchlist_id=watchlist_id, rule_type=rule_type, threshold=threshold, created_at=datetime.now(UTC)); session.add(row); session.commit(); session.refresh(row); return row

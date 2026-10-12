"""Small idempotent automation kernel; a scheduler may trigger it in production."""
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import (
    AlertRuleRecord,
    JobRecord,
    JobRunRecord,
    SessionLocal,
    WatchlistItemRecord,
    WatchlistRecord,
)


class AutomationService:
    def __init__(self, analysis_service, max_retries: int = 3):
        self.analysis_service, self.max_retries = analysis_service, max_retries

    def enqueue_eod(self, symbol: str, scheduled_for: datetime | None = None) -> JobRecord:
        scheduled = (scheduled_for or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
        with SessionLocal() as session:
            job = session.scalar(select(JobRecord).where(JobRecord.job_type == "eod", JobRecord.symbol == symbol.upper(), JobRecord.scheduled_for == scheduled))
            if job is None:
                now = datetime.now(UTC); job = JobRecord(job_type="eod", symbol=symbol.upper(), scheduled_for=scheduled, status="QUEUED", attempts=0, created_at=now, updated_at=now); session.add(job); session.commit(); session.refresh(job)
            return job

    async def run(self, job_id: int) -> JobRecord:
        with SessionLocal() as session:
            job = session.get(JobRecord, job_id)
            if job is None: raise LookupError("Job không tồn tại")
            if job.status == "SUCCESS": return job
            job.attempts += 1; job.status = "RUNNING"; job.updated_at = datetime.now(UTC)
            run = JobRunRecord(job_id=job.id, status="RUNNING", started_at=datetime.now(UTC)); session.add(run); session.commit()
        try:
            result = await self.analysis_service.analyze(job.symbol)
            with SessionLocal() as session:
                job = session.get(JobRecord, job_id); run = session.scalar(select(JobRunRecord).where(JobRunRecord.job_id == job_id).order_by(JobRunRecord.id.desc()))
                job.status = "SUCCESS"; job.updated_at = datetime.now(UTC); run.status = "SUCCESS"; run.finished_at = datetime.now(UTC); run.result_json = json.dumps({"evidence_count": result.evidence_count}, ensure_ascii=False); session.commit(); return job
        except Exception as exc:  # noqa: BLE001 - failed jobs must be persisted for retry
            with SessionLocal() as session:
                job = session.get(JobRecord, job_id); run = session.scalar(select(JobRunRecord).where(JobRunRecord.job_id == job_id).order_by(JobRunRecord.id.desc()))
                job.status = "FAILED" if job.attempts >= self.max_retries else "QUEUED"; job.last_error = str(exc)[:1024]; job.updated_at = datetime.now(UTC); run.status = "FAILED"; run.finished_at = datetime.now(UTC); run.error = str(exc)[:1024]; session.commit(); return job

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

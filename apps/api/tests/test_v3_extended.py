import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.automation import AutomationService
from app.config import Settings
from app.connectors.news import classify_event, group_hash, relevance
from app.database import JobRecord, JobRunRecord, SessionLocal, init_db
from app.schemas import Security


def test_news_pipeline_classifies_and_deduplicates_group():
    security = Security(symbol="HPG", name="Tập đoàn Hòa Phát", exchange="HOSE", aliases=["Hoa Phat"])
    assert classify_event("HPG công bố lợi nhuận quý mới") == "earnings"
    assert relevance("HPG tăng trưởng lợi nhuận", security) >= 0.7
    stamp = datetime(2025, 1, 2, tzinfo=UTC)
    assert group_hash("HPG lợi nhuận", stamp) == group_hash("HPG lợi nhuận", stamp)
    assert group_hash("HPG lợi nhuận", stamp) != group_hash("HPG lợi nhuận", datetime(2025, 1, 3, tzinfo=UTC))


def test_concurrent_job_claim_executes_once():
    init_db()
    scheduled = datetime.now(UTC).replace(second=0, microsecond=0)
    with SessionLocal() as session:
        old_jobs = session.scalars(select(JobRecord).where(JobRecord.symbol == "V4TEST")).all()
        for old_job in old_jobs:
            session.execute(delete(JobRunRecord).where(JobRunRecord.job_id == old_job.id))
            session.delete(old_job)
        job = JobRecord(job_type="eod", symbol="V4TEST", scheduled_for=scheduled, status="QUEUED", attempts=0, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    class FakeAnalysis:
        async def analyze(self, symbol):
            await asyncio.sleep(0.02)
            return SimpleNamespace(evidence_count=1)

    async def run_both():
        service = AutomationService(FakeAnalysis(), max_retries=3)
        return await asyncio.gather(service.run(job_id), service.run(job_id))

    results = asyncio.run(run_both())
    with SessionLocal() as session:
        persisted = session.get(JobRecord, job_id)
        runs = session.scalars(select(JobRunRecord).where(JobRunRecord.job_id == job_id)).all()
        assert persisted.status == "SUCCESS"
        assert persisted.attempts == 1
        assert len(runs) == 1
    assert any(result.status == "SUCCESS" for result in results)


def test_production_settings_fail_closed_without_strong_admin_secret():
    with pytest.raises(ValueError):
        Settings(app_environment="production", admin_api_token="short")

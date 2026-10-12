import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from app.automation import AutomationService
from app.claim_verification import ClaimVerificationService
from app.config import Settings
from app.connectors.news import classify_event, group_hash, relevance
from app.database import JobRecord, JobRunRecord, ReportSnapshotRecord, SessionLocal, init_db
from app.schemas import DailyMarketReport, EvidenceRecord, FinancialClaim, Security


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


def test_expired_worker_cannot_overwrite_new_owner_result():
    init_db()
    scheduled = datetime.now(UTC).replace(second=0, microsecond=0)
    with SessionLocal() as session:
        old_jobs = session.scalars(select(JobRecord).where(JobRecord.symbol == "LEASETEST")).all()
        for old_job in old_jobs:
            session.execute(delete(JobRunRecord).where(JobRunRecord.job_id == old_job.id))
            session.delete(old_job)
        job = JobRecord(
            job_type="eod",
            symbol="LEASETEST",
            scheduled_for=scheduled,
            status="QUEUED",
            attempts=0,
            created_at=scheduled,
            updated_at=scheduled,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    service = AutomationService(object(), max_retries=3, lease_seconds=10)
    first = service.claim(job_id, worker_id="worker-a", now=scheduled)
    assert first is not None
    second = service.claim(
        job_id, worker_id="worker-b", now=scheduled + timedelta(seconds=11)
    )
    assert second is not None

    service.complete_success(
        first,
        {"owner": "worker-a"},
        snapshot=DailyMarketReport(
            snapshot_key=f"stock-eod:{job_id}",
            report_type="stock_eod",
            symbol="LEASETEST",
            trading_date=scheduled,
            source_mode="fixture",
            sections={"owner": ["worker-a"]},
            created_at=scheduled,
        ),
        now=scheduled + timedelta(seconds=12),
    )
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        assert job.status == "RUNNING"
        assert job.worker_id == "worker-b"

    service.complete_success(
        second,
        {"owner": "worker-b"},
        snapshot=DailyMarketReport(
            snapshot_key=f"stock-eod:{job_id}",
            report_type="stock_eod",
            symbol="LEASETEST",
            trading_date=scheduled,
            source_mode="fixture",
            sections={"owner": ["worker-b"]},
            created_at=scheduled,
        ),
        now=scheduled + timedelta(seconds=12),
    )
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        runs = session.scalars(
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.id)
        ).all()
        assert job.status == "SUCCESS"
        assert [run.status for run in runs] == ["EXPIRED", "SUCCESS"]
        assert json.loads(runs[1].result_json) == {"owner": "worker-b"}
        snapshots = session.scalars(
            select(ReportSnapshotRecord).where(
                ReportSnapshotRecord.snapshot_key == f"stock-eod:{job_id}"
            )
        ).all()
        assert len(snapshots) == 1
        assert json.loads(snapshots[0].payload_json)["sections"]["owner"] == ["worker-b"]


def test_failed_job_uses_bounded_retry_backoff():
    init_db()
    scheduled = datetime.now(UTC).replace(second=0, microsecond=0)
    with SessionLocal() as session:
        job = JobRecord(
            job_type="eod",
            symbol="BACKOFF",
            scheduled_for=scheduled,
            status="QUEUED",
            attempts=0,
            created_at=scheduled,
            updated_at=scheduled,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    class FailingAnalysis:
        async def analyze(self, symbol):
            raise RuntimeError("controlled source failure")

    service = AutomationService(FailingAnalysis(), max_retries=3)
    first = asyncio.run(service.run(job_id))
    second = asyncio.run(service.run(job_id))
    assert first.status == second.status == "RETRY_PENDING"
    assert second.attempts == 1
    assert second.next_attempt_at is not None
    with SessionLocal() as session:
        runs = session.scalars(
            select(JobRunRecord).where(JobRunRecord.job_id == job_id)
        ).all()
        assert len(runs) == 1


def test_production_settings_fail_closed_without_strong_admin_secret():
    with pytest.raises(ValueError):
        Settings(app_environment="production", admin_api_token="short")


def test_ai_claim_verifier_rejects_wrong_evidence_identity_and_value():
    evidence = [
        EvidenceRecord(
            evidence_id="E001",
            kind="fact",
            statement="Giá quan sát 25.000 VND.",
            source="test-source",
            symbol="HPG",
            metric_key="latest_price",
            value=25_000,
            unit="vnd",
            period="2026-10-12",
        )
    ]
    base = {
        "claim_id": "C001",
        "claim_type": "financial_metric",
        "symbol": "HPG",
        "metric_key": "latest_price",
        "value": 25_000,
        "unit": "vnd",
        "period": "2026-10-12",
        "evidence_ids": ["E001"],
        "interpretation": "Giá đóng cửa được ghi nhận",
    }
    verifier = ClaimVerificationService()
    assert len(verifier.verify([FinancialClaim(**base)], evidence).accepted) == 1
    bad_value = FinancialClaim(**(base | {"value": 40_000}))
    assert verifier.verify([bad_value], evidence).rejected[0].code == "value_mismatch"
    bad_symbol = FinancialClaim(**(base | {"symbol": "FPT"}))
    assert verifier.verify([bad_symbol], evidence).rejected[0].code == "symbol_mismatch"

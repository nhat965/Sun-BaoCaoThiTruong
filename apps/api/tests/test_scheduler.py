import os
from datetime import UTC, datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient

from app.automation import AutomationService
from app.config import Settings
from app.database import JobRecord, SessionLocal, init_db
from app.main import app
from app.registry import seed_registry_if_empty
from app.scheduler import ProductionScheduler


def _settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:", market_data_mode="fixture",
        scheduler_daily_times="16:30", scheduler_batch_limit=100,
        admin_api_token="scheduler-test-token-long-enough",
    )


def test_scheduler_slot_and_enqueue_are_idempotent():
    init_db()
    seed_registry_if_empty()
    scheduler = ProductionScheduler(_settings(), worker_id="test-worker")
    now = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    first = scheduler.enqueue_due(now)
    second = scheduler.enqueue_due(now)
    assert first
    assert len(first) == len(second)
    with SessionLocal() as session:
        assert session.query(JobRecord).count() == len(first)
        assert all(row.idempotency_key for row in session.query(JobRecord).all())


def test_two_claimers_only_one_owns_job():
    init_db()
    service = AutomationService(None, max_retries=3, lease_seconds=60)
    job = service.enqueue_job(
        "CHECK_PROVIDER_HEALTH", scheduled_for=datetime.now(UTC),
        idempotency_key="test:health:once",
    )
    first = service.claim(job.id, worker_id="worker-a")
    second = service.claim(job.id, worker_id="worker-b")
    assert first is not None
    assert second is None


def test_dependency_gate_waits_for_upstream_terminal_states():
    init_db()
    service = AutomationService(None)
    slot = datetime(2026, 10, 12, 9, tzinfo=UTC)
    upstream = [
        service.enqueue_job(name, scheduled_for=slot, idempotency_key=f"dep:{name}")
        for name in ("SYNC_SECURITIES_MASTER", "SYNC_OHLCV", "SYNC_MARKET_INDICES")
    ]
    recalc = service.enqueue_job("RECALCULATE_MARKET_INTELLIGENCE", scheduled_for=slot, idempotency_key="dep:recalc")
    with SessionLocal() as session:
        assert ProductionScheduler._dependencies_ready(session, recalc) is False
        for row in upstream:
            session.get(JobRecord, row.id).status = "BLOCKED"
        session.commit()
        assert ProductionScheduler._dependencies_ready(session, session.get(JobRecord, recalc.id)) is True


def test_coverage_endpoint_reports_fixture_and_unknown_flow_without_inventing_values():
    init_db()
    seed_registry_if_empty()
    with TestClient(app) as client:
        response = client.get("/api/v1/data-quality/coverage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["market_data_mode"] == "fixture"
    assert payload["securities"]["active"] >= 1
    assert payload["ohlcv"]["foreign_flow_rows"] == 0
    assert payload["ohlcv"]["foreign_flow_status"].startswith("unavailable")
    index = payload["indices"]["VNINDEX"]
    assert isinstance(index["available"], bool)
    if index["available"]:
        assert index["provider"]
        assert index["latest_session"]

import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import MarketRiskSignalRecord, MarketScenarioSnapshotRecord, SessionLocal, init_db
from app.main import app
from app.market_trend import _aligned_index_change, _freshness
from app.sector_liquidity import (
    _aggregate_relative_volume,
    _relative_volume,
)


def _price_rows(count: int, *, start: datetime | None = None) -> list[SimpleNamespace]:
    start = start or datetime(2026, 10, 14, 2, tzinfo=UTC)
    return [
        SimpleNamespace(
            volume=2_000 + index * 10,
            market_timestamp=start - timedelta(days=index),
        )
        for index in range(count)
    ]


def test_rvol20_requires_a_complete_twenty_session_baseline():
    assert _relative_volume(_price_rows(20)) is None
    assert _relative_volume(_price_rows(21)) is not None

    sessions = [date(2026, 10, 14) - timedelta(days=index) for index in range(21)]
    volume_by_session = {session: 100 for session in sessions}
    volume_by_session[sessions[0]] = 200
    assert _aggregate_relative_volume(volume_by_session, sessions) == 2
    assert _aggregate_relative_volume(volume_by_session, sessions[:20]) is None


def test_freshness_is_stale_when_rows_exist_but_market_timestamp_is_old():
    old = SimpleNamespace(market_timestamp=datetime(2026, 10, 1, tzinfo=UTC))
    recent = SimpleNamespace(market_timestamp=datetime(2026, 10, 13, tzinfo=UTC))
    reference = datetime(2026, 10, 14, tzinfo=UTC)
    assert _freshness({1: old}, now=reference) == "stale"
    assert _freshness({1: recent}, now=reference) == "fresh"


def test_index_change_requires_an_observation_on_the_requested_session():
    rows = [
        SimpleNamespace(market_session_date=date(2026, 10, 13), close=120),
        SimpleNamespace(market_session_date=date(2026, 10, 12), close=100),
    ]
    assert _aligned_index_change(rows, date(2026, 10, 13)) == 20
    assert _aligned_index_change(rows, date(2026, 10, 14)) is None


def test_risk_and_scenario_replays_are_idempotent():
    init_db()
    with TestClient(app) as client:
        first_risks = client.get("/api/v1/market/risks")
        first_scenarios = client.get("/api/v1/market/scenarios")
        second_risks = client.get("/api/v1/market/risks")
        second_scenarios = client.get("/api/v1/market/scenarios")

    assert first_risks.status_code == second_risks.status_code == 200
    assert first_scenarios.status_code == second_scenarios.status_code == 200
    with SessionLocal() as session:
        assert session.scalar(select(func.count(MarketRiskSignalRecord.id))) == len(first_risks.json()["signals"])
        assert session.scalar(select(func.count(MarketScenarioSnapshotRecord.id))) == 3

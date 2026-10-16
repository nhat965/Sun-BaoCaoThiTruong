import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.connectors.base import ConnectorError
from app.connectors.fixture import FixtureConnector
from app.database import MarketRiskSignalRecord, MarketScenarioSnapshotRecord, SessionLocal, init_db
from app.freshness import assess_freshness
from app.main import _freshness_label, app
from app.market_trend import _aligned_index_change, _aligned_index_change_detail, _freshness
from app.registry import seed_registry_if_empty
from app.repositories import PriceRepository
from app.sector_liquidity import (
    _aggregate_relative_volume,
    _relative_volume,
)
from app.services import AnalysisService


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
    recent = SimpleNamespace(
        market_timestamp=datetime(2026, 10, 13, tzinfo=UTC),
        market_session_date=date(2026, 10, 13),
        source_mode="live",
        freshness="daily/delayed",
    )
    reference = datetime(2026, 10, 14, tzinfo=UTC)
    assert _freshness({1: old}, now=reference) == "stale"
    assert _freshness({1: recent}, now=reference) == "delayed"
    assert (
        _freshness_label(
            recent.market_timestamp,
            market_session_date=recent.market_session_date,
            source_mode=recent.source_mode,
            provider_freshness=recent.freshness,
            now=reference,
        )
        == "delayed"
    )


def test_freshness_distinguishes_fixture_and_unconfirmed_weekday_without_calendar():
    fixture = SimpleNamespace(
        market_timestamp=datetime(2026, 10, 13, tzinfo=UTC),
        market_session_date=date(2026, 10, 13),
        source_mode="fixture",
        freshness="fixture",
    )
    weekday = SimpleNamespace(
        market_timestamp=datetime(2026, 10, 13, tzinfo=UTC),
        market_session_date=date(2026, 10, 13),
        source_mode="live",
        freshness="unknown",
    )
    reference = datetime(2026, 10, 14, tzinfo=UTC)
    assert _freshness([fixture], now=reference) == "fixture"
    assert _freshness([weekday], now=reference) == "unconfirmed"
    assert assess_freshness(
        market_timestamp=weekday.market_timestamp,
        market_session_date=weekday.market_session_date,
        source_mode="live",
        now=reference,
        official_sessions=[date(2026, 10, 13)],
    ).status == "fresh"


def test_index_change_requires_an_observation_on_the_requested_session():
    rows = [
        SimpleNamespace(market_session_date=date(2026, 10, 13), close=120),
        SimpleNamespace(market_session_date=date(2026, 10, 12), close=100),
    ]
    assert _aligned_index_change(rows, date(2026, 10, 13)) == 20
    assert _aligned_index_change(rows, date(2026, 10, 14)) is None


def test_index_session_alignment_handles_weekend_and_suspicious_holiday_gap():
    monday_rows = [
        SimpleNamespace(market_session_date=date(2026, 10, 12), close=120),
        SimpleNamespace(market_session_date=date(2026, 10, 9), close=100),
    ]
    assert _aligned_index_change_detail(monday_rows, date(2026, 10, 12))[1] == "weekday_candidate_aligned"

    holiday_gap_rows = [
        SimpleNamespace(market_session_date=date(2026, 10, 13), close=120),
        SimpleNamespace(market_session_date=date(2026, 10, 9), close=100),
    ]
    value, status = _aligned_index_change_detail(holiday_gap_rows, date(2026, 10, 13))
    assert value is None
    assert status == "unconfirmed_gap"


def test_index_session_alignment_rejects_conflicting_provider_duplicates():
    rows = [
        SimpleNamespace(market_session_date=date(2026, 10, 13), close=120),
        SimpleNamespace(market_session_date=date(2026, 10, 13), close=121),
        SimpleNamespace(market_session_date=date(2026, 10, 12), close=100),
    ]
    value, status = _aligned_index_change_detail(rows, date(2026, 10, 13))
    assert value is None
    assert status == "duplicate_session_values"


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


def test_analysis_uses_persisted_ohlcv_when_upstream_is_unavailable(monkeypatch):
    init_db()
    seed_registry_if_empty()
    series = asyncio.run(FixtureConnector().prices("HPG", limit=35))
    with SessionLocal() as session:
        PriceRepository(session).upsert_series(series)
        session.commit()

    service = AnalysisService(
        Settings(database_url="sqlite:///:memory:", market_data_mode="fixture", news_feeds="")
    )

    async def unavailable(*args, **kwargs):
        raise ConnectorError("provider unavailable")

    monkeypatch.setattr(service.manager, "prices", unavailable)
    result = asyncio.run(service.analyze("HPG"))

    assert result.latest_price == result.prices.bars[-1].close
    assert result.prices.provenance.freshness == "historical"
    assert result.prices.provenance.delayed is True
    assert "persisted observations" in (result.prices.provenance.notes or "")
    assert any("không phải dữ liệu realtime" in item for item in result.limitations)

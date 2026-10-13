import os
from datetime import UTC, date, datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, get_settings
from app.database import MarketIndexObservationRecord, SessionLocal, init_db
from app.main import app
from app.market_foundation import VietnamMarketCalendar, canonical_market_universe

ADMIN_TOKEN = "market-foundation-admin-token-long-enough"


def _settings() -> Settings:
    return Settings(
        market_data_mode="fixture",
        admin_api_token=ADMIN_TOKEN,
        admin_rate_limit_per_minute=1000,
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def test_market_calendar_uses_vietnam_timezone_and_does_not_treat_weekends_as_missing_sessions():
    calendar = VietnamMarketCalendar()
    assert calendar.session_date(datetime(2026, 1, 2, 17, tzinfo=UTC)) == date(2026, 1, 3)
    assert calendar.classify(date(2026, 1, 3), "HOSE").status == "weekend"
    weekday = calendar.classify(date(2026, 1, 2), "HOSE")
    assert weekday.status == "trading_candidate"
    assert "holiday calendar" in weekday.limitations[0].lower()


def test_market_universe_reports_exchange_and_history_coverage_without_inventing_denominators():
    init_db()
    coverage = canonical_market_universe()
    assert coverage.universe_count >= coverage.active_count >= 1
    assert set(coverage.exchange_distribution).issubset({"HOSE", "HNX", "UPCOM"})
    assert coverage.history_20_count <= coverage.active_count
    assert coverage.history_50_count <= coverage.history_20_count
    assert coverage.history_200_count <= coverage.history_50_count
    assert coverage.market_cap_count == 0
    assert coverage.foreign_flow_count == 0


def test_authorized_index_import_is_idempotent_and_preserves_provenance():
    app.dependency_overrides[get_settings] = _settings
    init_db()
    csv = (
        "symbol,name,exchange,market_session_date,market_timestamp,close,previous_close,"
        "provider,source_url,retrieved_at,data_mode,validation_status,coverage,freshness,"
        "adjustment_policy\n"
        "VNINDEX,VN-Index,HOSE,2026-01-02,2026-01-02T09:00:00+07:00,1250.5,1240.0,"
        "authorized-index-feed,https://data.example/vnindex,2026-01-02T10:00:00+07:00,"
        "delayed,valid,full_market,daily,official_adjustment_policy\n"
    )
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/market/indices/import",
                headers=_headers() | {"X-Source-Name": "authorized-index-feed"},
                content=csv,
            )
            assert first.status_code == 200
            assert first.json()["inserted"] == 1

            replay = client.post(
                "/api/v1/market/indices/import",
                headers=_headers() | {"X-Source-Name": "authorized-index-feed"},
                content=csv,
            )
            assert replay.status_code == 200
            assert replay.json()["skipped"] == 1

            response = client.get("/api/v1/market/indices")
            assert response.status_code == 200
            payload = response.json()
            assert payload["data_status"] == "available"
            assert payload["indices"][0]["symbol"] == "VNINDEX"
            assert payload["indices"][0]["provider"] == "authorized-index-feed"
            assert payload["indices"][0]["data_mode"] == "delayed"
            assert payload["indices"][0]["source_url"] == "https://data.example/vnindex"

        with SessionLocal() as session:
            rows = session.scalars(select(MarketIndexObservationRecord)).all()
            assert len(rows) == 1
            assert rows[0].market_session_date == date(2026, 1, 2)
    finally:
        app.dependency_overrides.clear()

import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import (
    MarketBreadthSnapshotRecord,
    MarketRegimeSnapshotRecord,
    SessionLocal,
    init_db,
)
from app.main import app


def test_market_breadth_reports_denominators_and_historical_points():
    init_db()
    with TestClient(app) as client:
        response = client.get("/api/v1/market/breadth")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_status"] in {"available", "partial", "unavailable"}
    assert "universe_count" in payload["coverage"]
    assert "ma20_eligible_count" in payload["coverage"]
    if payload["data_status"] != "unavailable":
        assert payload["above_ma20_denominator"] is not None
        assert payload["above_ma20_percent"] is None or 0 <= payload["above_ma20_percent"] <= 100
        assert isinstance(payload["historical"], list)


def test_market_regime_exposes_evidence_without_probability_claims():
    init_db()
    with TestClient(app) as client:
        response = client.get("/api/v1/market/regime")
    assert response.status_code == 200
    payload = response.json()
    assert payload["regime"] in {"UPTREND", "DOWNTREND", "SIDEWAYS", "VOLATILE", "UNCERTAIN"}
    assert "probability" not in payload["indicators"]
    assert any("backtest" in item.lower() for item in payload["limitations"])


def test_market_breadth_and_regime_snapshots_are_upserted_by_session():
    init_db()
    with TestClient(app) as client:
        breadth = client.get("/api/v1/market/breadth").json()
        regime = client.get("/api/v1/market/regime").json()
        client.get("/api/v1/market/breadth")
        client.get("/api/v1/market/regime")
    with SessionLocal() as session:
        if breadth["market_session"]:
            assert (
                session.scalar(
                    select(func.count(MarketBreadthSnapshotRecord.id)).where(
                        MarketBreadthSnapshotRecord.market_session_date
                        == date.fromisoformat(breadth["market_session"]),
                        MarketBreadthSnapshotRecord.formula_version == "market-breadth-v1",
                    )
                )
                == 1
            )
        if regime["market_session"]:
            assert (
                session.scalar(
                    select(func.count(MarketRegimeSnapshotRecord.id)).where(
                        MarketRegimeSnapshotRecord.market_session_date
                        == date.fromisoformat(regime["market_session"]),
                        MarketRegimeSnapshotRecord.formula_version == "market-regime-v1",
                    )
                )
                == 1
            )

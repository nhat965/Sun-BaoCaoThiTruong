import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import MarketRiskSignalRecord, MarketScenarioSnapshotRecord, SessionLocal, init_db
from app.main import app


def test_risks_expose_triggers_and_limitations_without_probability_claims():
    init_db()
    with TestClient(app) as client:
        response = client.get("/api/v1/market/risks")
    assert response.status_code == 200
    payload = response.json()
    assert "signals" in payload
    assert "probability" not in payload
    for signal in payload["signals"]:
        assert signal["severity"] in {"info", "watch", "warning"}
        assert signal["trigger"]
        assert signal["evidence"]
        assert "limitations" in signal


def test_scenarios_have_three_conditional_paths_and_no_probability():
    init_db()
    with TestClient(app) as client:
        response = client.get("/api/v1/market/scenarios")
    assert response.status_code == 200
    payload = response.json()
    assert {item["scenario_id"] for item in payload["scenarios"]} == {"base", "positive", "negative"}
    assert "probability" not in payload
    for item in payload["scenarios"]:
        assert item["assumptions"]
        assert item["evidence"]
        assert item["invalidation_conditions"]


def test_risk_and_scenario_snapshots_are_idempotent():
    init_db()
    with TestClient(app) as client:
        risks = client.get("/api/v1/market/risks").json()
        scenarios = client.get("/api/v1/market/scenarios").json()
        client.get("/api/v1/market/risks")
        client.get("/api/v1/market/scenarios")
    with SessionLocal() as session:
        if risks["market_session"]:
            session_date = date.fromisoformat(risks["market_session"])
            assert session.scalar(select(func.count(MarketRiskSignalRecord.id)).where(MarketRiskSignalRecord.market_session_date == session_date, MarketRiskSignalRecord.formula_version == "market-risk-v1")) == len(risks["signals"])
        if scenarios["market_session"]:
            session_date = date.fromisoformat(scenarios["market_session"])
            assert session.scalar(select(func.count(MarketScenarioSnapshotRecord.id)).where(MarketScenarioSnapshotRecord.market_session_date == session_date, MarketScenarioSnapshotRecord.formula_version == "market-scenario-v1")) == 3

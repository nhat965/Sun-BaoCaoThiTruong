import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient

from app.main import app


def test_market_report_contains_engine_evidence_and_limitations():
    admin = {"Authorization": "Bearer test-admin-token"}
    with TestClient(app) as client:
        response = client.post("/api/v1/market/reports/post_market?trading_date=2026-10-12", headers=admin)
    assert response.status_code == 200
    payload = response.json()
    assert {"breadth", "regime", "liquidity", "risks", "scenarios", "provenance", "limitations"}.issubset(payload["sections"])
    assert payload["sections"]["provenance"]
    assert payload["sections"]["limitations"]
    assert all("probability" not in item.lower() for item in payload["sections"]["scenarios"])

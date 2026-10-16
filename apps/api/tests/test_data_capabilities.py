"""Capability audit tests: persisted rows are not silently promoted to live data."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import init_db
from app.main import app
from app.registry import seed_registry_if_empty


def _settings() -> Settings:
    return Settings(database_url="sqlite:///:memory:", market_data_mode="fixture")


def test_capability_audit_labels_fixture_and_missing_live_sources():
    init_db()
    seed_registry_if_empty()
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/data-platform/capabilities")
        assert response.status_code == 200
        payload = response.json()
        rows = {item["capability"]: item for item in payload["capabilities"]}
        assert rows["securities_metadata"]["records"] >= 13
        assert rows["securities_metadata"]["status"] == "IMPLEMENTED_FILE_VERIFIED"
        assert rows["historical_ohlcv"]["status"] == "IMPLEMENTED_MOCK_TESTED"
        assert rows["foreign_flow"]["status"] in {
            "BLOCKED_EXTERNAL_DEPENDENCY",
            "NOT_IMPLEMENTED",
        }
        assert payload["market_data_mode"] == "fixture"
        assert payload["providers"]
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_report_is_explicit_about_external_baseline():
    init_db()
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/data-quality/reconciliation")
        assert response.status_code == 200
        payload = response.json()
        assert payload["unresolved_external_baseline"] is True
        assert {item["dataset"] for item in payload["datasets"]} >= {
            "securities",
            "ohlcv",
            "financials",
            "corporate_actions",
        }
        assert all(item["records_before"] is None for item in payload["datasets"])
    finally:
        app.dependency_overrides.clear()


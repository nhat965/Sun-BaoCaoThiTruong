"""End-to-end acceptance on explicitly labelled fixture data.

This suite proves application behavior without claiming live-market coverage.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import Settings, get_settings
from app.database import PriceObservation, SecurityRecord, SessionLocal, init_db
from app.main import app
from app.registry import seed_registry_if_empty

ADMIN_TOKEN = "release-acceptance-admin-token-long-enough"


def _settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        market_data_mode="fixture",
        admin_api_token=ADMIN_TOKEN,
        admin_rate_limit_per_minute=1000,
    )


def test_fixture_release_flow_registry_sync_coverage_admin_and_replay():
    init_db()
    seed_registry_if_empty()
    with SessionLocal() as session:
        hpg_id = session.scalar(select(SecurityRecord.id).where(SecurityRecord.symbol == "HPG"))
        session.execute(delete(PriceObservation).where(
            PriceObservation.security_id == hpg_id,
            PriceObservation.provider == "Synthetic fixture (development only)",
        ))
        session.commit()
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            registry = client.get("/api/v1/securities", params={"page": 1, "page_size": 100})
            assert registry.status_code == 200
            assert registry.json()["total"] >= 13
            assert any(item["symbol"] == "HPG" for item in registry.json()["items"])

            unauthenticated = client.get("/api/v1/admin/operations")
            assert unauthenticated.status_code == 401

            headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
            first = client.post("/api/v1/sync/prices/HPG", params={"provider": "fixture", "limit": 60}, headers=headers)
            replay = client.post("/api/v1/sync/prices/HPG", params={"provider": "fixture", "limit": 60}, headers=headers)
            assert first.status_code == replay.status_code == 200
            assert first.json()["inserted_count"] == 60
            assert replay.json()["inserted_count"] == 0
            assert replay.json()["sync_mode"] == "incremental"

            coverage = client.get("/api/v1/data-quality/coverage")
            assert coverage.status_code == 200
            payload = coverage.json()
            assert payload["market_data_mode"] == "fixture"
            assert payload["ohlcv"]["symbols_with_price"] >= 1
            assert payload["ohlcv"]["foreign_flow_status"].startswith("unavailable")

            operations = client.get("/api/v1/admin/operations", headers=headers)
            assert operations.status_code == 200
            assert operations.json()["scheduler"]["timezone"] == "Asia/Ho_Chi_Minh"
    finally:
        app.dependency_overrides.clear()

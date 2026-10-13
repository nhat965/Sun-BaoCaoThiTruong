import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import LiquiditySnapshotRecord, SectorSnapshotRecord, SessionLocal, init_db
from app.main import app


def test_sector_endpoint_keeps_taxonomy_and_value_coverage_explicit():
    init_db()
    with TestClient(app) as client:
        response = client.get("/api/v1/market/sectors", params={"sort_by": "liquidity"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_status"] in {"available", "partial", "unavailable"}
    assert "taxonomy_coverage_percent" in payload["coverage"]
    for sector in payload["sectors"]:
        assert sector["taxonomy_version"]
        assert sector["estimated_trading_value"] is None
        assert "actual_trading_value_count" in sector["coverage"]
        assert isinstance(sector["limitations"], list)


def test_sector_detail_and_liquidity_do_not_infer_foreign_flow():
    init_db()
    with TestClient(app) as client:
        sectors = client.get("/api/v1/market/sectors").json()
        if sectors["sectors"]:
            sector_id = sectors["sectors"][0]["sector_id"]
            detail = client.get(f"/api/v1/market/sectors/{sector_id}")
            assert detail.status_code == 200
            assert all(item["sector_id"] == sector_id for item in detail.json()["sectors"])
        liquidity = client.get("/api/v1/market/liquidity")
    assert liquidity.status_code == 200
    payload = liquidity.json()
    assert payload["foreign_net_value"] is None
    assert payload["top10_trading_value_share_percent"] is None or 0 <= payload["top10_trading_value_share_percent"] <= 100
    assert any("foreign" in item.lower() for item in payload["limitations"])


def test_sector_and_liquidity_snapshots_are_upserted():
    init_db()
    with TestClient(app) as client:
        sectors = client.get("/api/v1/market/sectors").json()
        liquidity = client.get("/api/v1/market/liquidity").json()
        client.get("/api/v1/market/sectors")
        client.get("/api/v1/market/liquidity")
    with SessionLocal() as session:
        if sectors["market_session"]:
            session_date = date.fromisoformat(sectors["market_session"])
            assert session.scalar(
                select(func.count(SectorSnapshotRecord.id)).where(
                    SectorSnapshotRecord.market_session_date == session_date,
                    SectorSnapshotRecord.formula_version == "sector-intelligence-v1",
                )
            ) == len(sectors["sectors"])
        if liquidity["market_session"]:
            assert session.scalar(
                select(func.count(LiquiditySnapshotRecord.id)).where(
                    LiquiditySnapshotRecord.market_session_date == date.fromisoformat(liquidity["market_session"]),
                    LiquiditySnapshotRecord.formula_version == "liquidity-intelligence-v1",
                )
            ) == 1

import asyncio
import os
from datetime import UTC, datetime

import pytest

os.environ["ADMIN_API_TOKEN"] = "test-admin-token"
os.environ["READER_API_TOKEN"] = "test-reader-token"
os.environ["ADMIN_RATE_LIMIT_PER_MINUTE"] = "30"

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.connectors.base import ConnectorError, MarketDataConnector
from app.connectors.manager import CircuitRegistry, ConnectorManager
from app.main import app
from app.schemas import PriceBar, PriceSeries, Provenance, Security

get_settings.cache_clear()


def test_import_requires_auth_and_role_and_validates_csv():
    with TestClient(app) as client:
        missing = client.post(
            "/api/v1/securities/import", content="symbol,name,exchange\nV3A,Alpha,HOSE\n"
        )
        assert missing.status_code == 401

        reader = client.post(
            "/api/v1/securities/import",
            headers={"Authorization": "Bearer test-reader-token"},
            content="symbol,name,exchange\nV3A,Alpha,HOSE\n",
        )
        assert reader.status_code == 403

        invalid = client.post(
            "/api/v1/securities/import",
            headers={"Authorization": "Bearer test-admin-token"},
            content="symbol,name\nV3A,Alpha\n",
        )
        assert invalid.status_code == 422

        valid = client.post(
            "/api/v1/securities/import",
            headers={"Authorization": "Bearer test-admin-token"},
            content="symbol,name,exchange\nV3A,Alpha,HOSE\n",
        )
        assert valid.status_code == 200
        assert valid.json()["inserted"] + valid.json()["updated"] == 1


class ControlledConnector(MarketDataConnector):
    name = "controlled-provider"

    def __init__(self) -> None:
        self.fail = True
        self.calls = 0

    async def search(self, query: str) -> list[Security]:
        return []

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        self.calls += 1
        if self.fail:
            raise ConnectorError("controlled failure")
        bar = PriceBar(
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            open=10,
            high=11,
            low=9,
            close=10,
            volume=100,
        )
        return PriceSeries(
            security=Security(symbol="AAA", name="Alpha", exchange="HOSE"),
            interval="1d",
            adjusted=False,
            bars=[bar],
            provenance=Provenance(
                source=self.name,
                provider_symbol="AAA.TEST",
                retrieved_at=datetime.now(UTC),
                mode="fixture",
            ),
        )


def test_circuit_breaker_persists_across_manager_instances_and_recovers():
    registry = CircuitRegistry()
    settings = Settings(
        database_url="sqlite:///:memory:",
        market_data_mode="live",
        circuit_failure_threshold=2,
        circuit_cooldown_seconds=0.5,
    )
    first = ControlledConnector()
    manager_one = ConnectorManager(settings, registry=registry)
    manager_one.providers = [first]
    with pytest.raises(ConnectorError):
        asyncio.run(manager_one.prices("AAA"))
    manager_two = ConnectorManager(settings, registry=registry)
    manager_two.providers = [first]
    with pytest.raises(ConnectorError):
        asyncio.run(manager_two.prices("AAA"))

    blocked_manager = ConnectorManager(settings, registry=registry)
    blocked_manager.providers = [first]
    with pytest.raises(ConnectorError, match="circuit open"):
        asyncio.run(blocked_manager.prices("AAA"))
    assert first.calls == 2

    import time

    time.sleep(0.55)
    first.fail = False
    recovered = ConnectorManager(settings, registry=registry)
    recovered.providers = [first]
    result = asyncio.run(recovered.prices("AAA"))
    assert result.security.symbol == "AAA"
    assert registry.states[first.name].state == "closed"


def test_financial_statement_csv_pipeline_and_relative_valuation():
    with TestClient(app) as client:
        admin = {"Authorization": "Bearer test-admin-token"}
        security = client.post(
            "/api/v1/securities/import",
            headers=admin,
            content="symbol,name,exchange\nV3B,Beta,HOSE\n",
        )
        assert security.status_code == 200
        content = """period_end,period_type,fiscal_year,statement_type,item_code,value,verification_status,statement_scope,statement_status
2023-12-31T00:00:00+00:00,year,2023,income,revenue,100,verified,consolidated,original
2023-12-31T00:00:00+00:00,year,2023,income,net_income,10,verified,consolidated,original
2023-12-31T00:00:00+00:00,year,2023,balance,total_assets,100,verified,consolidated,original
2023-12-31T00:00:00+00:00,year,2023,balance,total_equity,50,verified,consolidated,original
2024-12-31T00:00:00+00:00,year,2024,income,revenue,120,verified,consolidated,amended
2024-12-31T00:00:00+00:00,year,2024,income,net_income,15,verified,consolidated,amended
2024-12-31T00:00:00+00:00,year,2024,balance,total_assets,110,verified,consolidated,amended
2024-12-31T00:00:00+00:00,year,2024,balance,total_equity,55,verified,consolidated,amended
2024-12-31T00:00:00+00:00,year,2024,income,revenue,80,verified,separate,original
"""
        imported = client.post(
            "/api/v1/stocks/V3B/financials/import",
            headers=admin | {"X-Source-Name": "authorized-financial-export"},
            content=content,
        )
        assert imported.status_code == 200
        assert imported.json()["inserted_periods"] == 3
        fundamentals = client.get("/api/v1/stocks/V3B/fundamentals")
        assert fundamentals.status_code == 200
        assert fundamentals.json()["metrics"]["revenue_growth_percent"] == 20
        assert fundamentals.json()["statement_scope"] == "consolidated"
        assert fundamentals.json()["statement_status"] == "amended"
        history = client.get("/api/v1/stocks/V3B/fundamentals/history")
        assert history.status_code == 200
        assert len(history.json()["periods"]) == 2
        assert history.json()["periods"][1]["metrics"]["revenue_growth_percent"] == 20
        assert history.json()["warnings"]
        valuation = client.post(
            "/api/v1/fundamentals/valuation",
            json={"symbol": "V3B", "eps": 3, "bvps": 11, "pe_multiple": 10, "pb_multiple": 1.5},
        )
        assert valuation.status_code == 200
        assert valuation.json()["scenarios"]["base"] == 23.25
        dcf = client.post(
            "/api/v1/fundamentals/valuation/dcf",
            json={
                "symbol": "V3B",
                "forecast_free_cash_flows": [100, 110],
                "discount_rate": 0.1,
                "terminal_growth_rate": 0.03,
                "net_debt": 50,
                "shares_outstanding": 10,
            },
        )
        assert dcf.status_code == 200
        assert dcf.json()["method"] == "dcf-fcf"
        invalid_dcf = client.post(
            "/api/v1/fundamentals/valuation/dcf",
            json={
                "symbol": "V3B",
                "forecast_free_cash_flows": [100],
                "discount_rate": 0.03,
                "terminal_growth_rate": 0.03,
                "shares_outstanding": 10,
            },
        )
        assert invalid_dcf.status_code == 422

        blocked_persist = client.post(
            "/api/v1/fundamentals/valuation/persist",
            json={"symbol": "V3B", "eps": 2.0, "bvps": 10.0, "pe_multiple": 10.0, "pb_multiple": 2.0},
        )
        assert blocked_persist.status_code == 401
        persisted = client.post(
            "/api/v1/fundamentals/valuation/persist",
            headers={"Authorization": "Bearer test-admin-token"},
            json={"symbol": "V3B", "eps": 2.0, "bvps": 10.0, "pe_multiple": 10.0, "pb_multiple": 2.0},
        )
        assert persisted.status_code == 200

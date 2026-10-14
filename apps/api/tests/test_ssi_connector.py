import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_DATA_MODE", "fixture")

import httpx
import pytest

from app.config import Settings
from app.connectors.base import ConnectorError
from app.connectors.ssi import SsiFastConnectConnector
from app.database import init_db
from app.registry import import_securities_csv


def test_ssi_connector_blocks_without_contract_endpoint():
    connector = SsiFastConnectConnector(Settings())
    with pytest.raises(ConnectorError, match="BLOCKED"):
        asyncio.run(connector.prices("HPG"))


def test_ssi_connector_parses_mocked_documented_token_and_ohlc_flow():
    init_db()
    import_securities_csv("symbol,name,exchange\nSIF,SSI Fixture,HOSE\n", "test")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            return httpx.Response(200, json={"data": {"accessToken": "test-token"}})
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "tradingDate": "2026-10-12T07:45:00+00:00",
                        "openPrice": 10,
                        "highPrice": 11,
                        "lowPrice": 9,
                        "closePrice": 10.5,
                        "volume": 1000,
                        "value": 10500,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        return httpx.AsyncClient(transport=transport, **kwargs)

    settings = Settings(
        ssi_api_key="key",
        ssi_api_secret="secret",
        ssi_auth_url="https://ssi.test/auth/token",
        ssi_ohlc_endpoint_template="https://ssi.test/ohlc/{symbol}",
    )
    connector = SsiFastConnectConnector(settings, client_factory=factory)
    result = asyncio.run(connector.prices("SIF", limit=10))
    assert result.provenance.provider_id == "ssi_fastconnect"
    assert result.provenance.mode == "live"
    assert result.bars[0].actual_trading_value == 10500

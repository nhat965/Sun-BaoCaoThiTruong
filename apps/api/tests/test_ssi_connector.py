import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_DATA_MODE", "fixture")

import httpx
import pytest

import app.connectors.ssi as ssi_module
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


def test_ssi_connector_uses_official_sdk_daily_ohlc_when_contract_endpoint_is_blank(monkeypatch):
    init_db()
    import_securities_csv("symbol,name,exchange\nSDK,SSI SDK Fixture,HOSE\n", "test")

    class FakeClient:
        def __init__(self, config):
            assert config.url == "https://fc-data.ssi.com.vn/"
            assert config.consumerID == "consumer"

        def daily_ohlc(self, config, request):
            assert request.symbol == "SDK"
            return {
                "status": 200,
                "data": [
                    {
                        "TradingDate": "15/10/2026",
                        "Open": 10,
                        "High": 11,
                        "Low": 9,
                        "Close": 10.5,
                        "Volume": 1000,
                        "Value": 10500,
                    }
                ],
            }

    fake_model = SimpleNamespace(
        daily_ohlc=lambda symbol, from_date, to_date, page, size, ascending: SimpleNamespace(
            symbol=symbol
        )
    )
    monkeypatch.setattr(ssi_module, "_ssi_sdk_client", SimpleNamespace(MarketDataClient=FakeClient))
    monkeypatch.setattr(ssi_module, "_ssi_sdk_model", fake_model)

    connector = SsiFastConnectConnector(
        Settings(
            ssi_api_key="consumer",
            ssi_api_secret="secret",
            ssi_data_base_url="https://fc-data.ssi.com.vn/",
        )
    )
    result = asyncio.run(connector.prices("SDK", limit=10))
    assert result.provenance.provider_id == "ssi_fastconnect"
    assert result.provenance.source_url.endswith("/api/v2/Market/DailyOhlc")
    assert result.bars[0].close == 10.5


def test_ssi_connector_normalizes_official_sdk_securities_and_indices(monkeypatch):
    init_db()

    class FakeClient:
        def __init__(self, config):
            pass

        def securities(self, config, request):
            return {
                "status": 200,
                "data": [
                    {"Symbol": "SDK", "StockName": "SSI SDK Fixture", "Market": request.market}
                ],
            }

        def daily_index(self, config, request):
            return {
                "status": 200,
                "data": [
                    {
                        "IndexDate": "15/10/2026",
                        "IndexValue": 1200,
                        "PreviousClose": 1190,
                    }
                ],
            }

    fake_model = SimpleNamespace(
        securities=lambda market, page, size: SimpleNamespace(market=market),
        daily_index=lambda *args: SimpleNamespace(indexId=args[1]),
    )
    monkeypatch.setattr(ssi_module, "_ssi_sdk_client", SimpleNamespace(MarketDataClient=FakeClient))
    monkeypatch.setattr(ssi_module, "_ssi_sdk_model", fake_model)

    connector = SsiFastConnectConnector(
        Settings(ssi_api_key="consumer", ssi_api_secret="secret")
    )
    securities = asyncio.run(connector.securities_metadata(("HOSE",)))
    indices = asyncio.run(connector.market_indices())
    assert securities[0].symbol == "SDK"
    assert securities[0].exchange == "HOSE"
    assert {item["symbol"] for item in indices} == {"VNINDEX", "VN30", "HNX", "UPCOM"}
    assert indices[0]["close"] == 1200

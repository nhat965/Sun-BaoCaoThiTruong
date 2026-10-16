import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.connectors.vnstock as vnstock_module
from app.config import Settings
from app.connectors.base import ConnectorError
from app.connectors.vnstock import VnstockConnector
from app.schemas import Security


class FakeFrame:
    def __init__(self, rows, source="vci"):
        self.rows = rows
        self.attrs = {"source": source}

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class FakeMarket:
    def equity(self, symbol):
        return SimpleNamespace(
            ohlcv=lambda **kwargs: FakeFrame([
                {"time": "2026-10-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000},
                {"time": "2026-10-15", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 1200, "value": 13_800},
                {"time": "2026-10-16", "open": None, "high": 12, "low": 10, "close": 11, "volume": 900},
            ])
        )

    def index(self, symbol):
        return SimpleNamespace(
            ohlcv=lambda **kwargs: FakeFrame([
                {"time": "2026-10-15", "close": 1300},
            ])
        )


class FakeReference:
    class Equity:
        def list_by_exchange(self, **kwargs):
            return FakeFrame([
                {"symbol": "HPG", "organ_name": "Hoa Phat Group", "exchange": "HOSE", "icb_name": "Materials"},
                {"symbol": "FPT", "org_name": "FPT Corp", "exchange": "HOSE"},
            ])

    def __init__(self):
        self.equity = self.Equity()


def _security():
    return Security(symbol="HPG", name="Hoa Phat Group", exchange="HOSE")


def test_vnstock_blocks_when_optional_package_is_unavailable(monkeypatch):
    monkeypatch.setattr(vnstock_module, "_VnMarket", None)
    monkeypatch.setattr(vnstock_module, "_VnReference", None)
    with pytest.raises(ConnectorError, match="BLOCKED"):
        asyncio.run(VnstockConnector(Settings()).prices("HPG"))


def test_vnstock_normalizes_equity_bars_without_fabricating_missing_values(monkeypatch):
    monkeypatch.setattr(vnstock_module, "_VnMarket", FakeMarket)
    monkeypatch.setattr(vnstock_module.VnstockConnector, "_resolve", lambda self, symbol: _security())
    result = asyncio.run(VnstockConnector(Settings()).prices("HPG", limit=10))
    assert [bar.close for bar in result.bars] == [10_500, 11_500]
    assert result.bars[-1].actual_trading_value == 13_800
    assert result.provenance.provider_id == "vnstock"
    assert result.provenance.source == "Vnstock v5 (vci)"
    assert result.provenance.mode == "live"
    assert result.adjusted is True


def test_vnstock_incremental_fetch_uses_recent_cursor_window(monkeypatch):
    monkeypatch.setattr(vnstock_module, "_VnMarket", FakeMarket)
    monkeypatch.setattr(vnstock_module.VnstockConnector, "_resolve", lambda self, symbol: _security())
    result = asyncio.run(
        VnstockConnector(Settings()).prices_since(
            "HPG", datetime(2026, 10, 14, tzinfo=UTC), limit=520
        )
    )
    assert [bar.timestamp.date().isoformat() for bar in result.bars] == ["2026-10-15"]
    assert "bounded reconciliation window" in (result.provenance.notes or "")


def test_vnstock_normalizes_reference_and_index_records(monkeypatch):
    monkeypatch.setattr(vnstock_module, "_VnMarket", FakeMarket)
    monkeypatch.setattr(vnstock_module, "_VnReference", FakeReference)
    connector = VnstockConnector(Settings())
    securities = asyncio.run(connector.securities_metadata(("HOSE",)))
    indices = asyncio.run(connector.market_indices())
    assert {item.symbol for item in securities} == {"HPG", "FPT"}
    assert {item["symbol"] for item in indices} == {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}
    assert indices[0]["close"] == 1300
    assert indices[0]["market_session_date"].isoformat() == "2026-10-15"

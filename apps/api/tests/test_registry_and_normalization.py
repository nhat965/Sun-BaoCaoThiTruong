from datetime import UTC, datetime

import pytest

from app.connectors.base import ConnectorError
from app.normalization import normalize_price_series
from app.registry import import_securities_csv
from app.schemas import PriceBar, PriceSeries, Provenance, Security


def series(bars: list[PriceBar]) -> PriceSeries:
    return PriceSeries(
        security=Security(symbol="HPG", name="Hòa Phát", exchange="HOSE"),
        interval="1d",
        adjusted=False,
        bars=bars,
        provenance=Provenance(
            source="test",
            provider_symbol="HPG.TEST",
            retrieved_at=datetime.now(UTC),
            mode="fixture",
        ),
    )


def test_rejects_invalid_ohlc_and_negative_volume():
    bad = PriceBar(timestamp=datetime.now(UTC), open=10, high=9, low=8, close=11, volume=-1)
    with pytest.raises(ConnectorError, match="OHLCV không hợp lệ"):
        normalize_price_series(series([bad]))


def test_normalization_sorts_and_deduplicates():
    first = PriceBar(
        timestamp=datetime(2025, 1, 2, tzinfo=UTC),
        open=10,
        high=12,
        low=9,
        close=11,
        volume=10,
    )
    second = first.model_copy(update={"timestamp": datetime(2025, 1, 1, tzinfo=UTC)})
    result = normalize_price_series(series([first, second, first]))
    assert [bar.timestamp.day for bar in result.bars] == [1, 2]
    assert result.provenance.validation_status == "valid"


def test_csv_import_validates_rows_and_supports_aliases():
    content = """symbol,name,aliases,exchange,listing_status,provider_symbol
AAA,Công ty Á Âu,A Au|Á Âu,HNX,active,AAA.VN
BAD,Thiếu sàn,,INVALID,active,BAD.VN
"""
    result = import_securities_csv(content, "authorized-test-export")
    assert result.inserted == 1
    assert result.rejected == 1
    assert result.errors

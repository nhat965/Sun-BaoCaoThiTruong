import json
import os
from datetime import UTC, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from app.connectors.base import ConnectorError
from app.database import PriceObservation, SecurityRecord, SessionLocal, init_db
from app.normalization import normalize_price_series
from app.registry import import_securities_csv, import_securities_xlsx
from app.repositories import PriceRepository, SecuritiesRepository
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


def test_normalization_records_conflicting_duplicate_and_allows_empty_incremental():
    first = PriceBar(
        timestamp=datetime(2025, 1, 2, tzinfo=UTC),
        open=10,
        high=12,
        low=9,
        close=11,
        volume=10,
    )
    corrected = first.model_copy(update={"close": 11.5})
    duplicate = normalize_price_series(series([first, corrected]))
    assert duplicate.bars[-1].close == 11.5
    assert "conflicting OHLCV" in duplicate.provenance.notes

    empty = series([]).model_copy(
        update={
            "provenance": series([]).provenance.model_copy(
                update={"market_timestamp": first.timestamp}
            )
        }
    )
    result = normalize_price_series(empty, allow_empty=True)
    assert result.bars == []
    assert result.provenance.market_timestamp == first.timestamp


def test_csv_import_validates_rows_and_supports_aliases():
    content = """symbol,name,aliases,exchange,listing_status,provider_symbol
AAA,Công ty Á Âu,A Au|Á Âu,HNX,active,AAA.VN
BAD,Thiếu sàn,,INVALID,active,BAD.VN
"""
    result = import_securities_csv(content, "authorized-test-export")
    assert result.inserted == 1
    assert result.rejected == 1
    assert result.errors


def test_xlsx_import_supports_provider_ids_and_rejects_batch_duplicates():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["symbol", "name", "exchange", "provider_ids", "listing_status"])
    sheet.append(["XLS1", "Công ty XLS", "UPCOM", '{"fireant":"fa-1"}', "active"])
    sheet.append(["XLS1", "Bản trùng", "HNX", "", "active"])
    content = BytesIO()
    workbook.save(content)

    result = import_securities_xlsx(content.getvalue(), "authorized-xlsx")
    assert result.inserted == 1
    assert result.rejected == 1
    assert "duplicate symbol" in result.errors[0]
    with SessionLocal() as session:
        security = SecuritiesRepository(session).get("XLS1")
        assert security is not None
        assert security.exchange == "UPCOM"
        assert security.provider_ids == {"fireant": "fa-1"}


def test_price_quality_flags_are_persisted_and_updated_idempotently():
    init_db()
    import_securities_csv("symbol,name,exchange\nQLT,Quality Test,HNX\n", "test")
    first = PriceBar(
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        open=10,
        high=11,
        low=9,
        close=10,
        volume=100,
    )
    second = PriceBar(
        timestamp=datetime(2025, 1, 10, tzinfo=UTC),
        open=14,
        high=16,
        low=13,
        close=15,
        volume=0,
    )
    price_series = series([first, second]).model_copy(
        update={"security": Security(symbol="QLT", name="Quality Test", exchange="HNX")}
    )
    with SessionLocal() as session:
        repository = PriceRepository(session)
        assert repository.upsert_series(price_series) == 2
        session.commit()
    with SessionLocal() as session:
        repository = PriceRepository(session)
        assert repository.upsert_series(price_series) == 0
        session.commit()
        rows = session.scalars(
            select(PriceObservation)
            .join(SecurityRecord, PriceObservation.security_id == SecurityRecord.id)
            .where(SecurityRecord.symbol == "QLT")
            .order_by(PriceObservation.market_timestamp)
        ).all()
        flags = json.loads(rows[-1].quality_flags_json)
        assert "zero_volume" in flags
        assert "price_jump_over_20_percent" in flags
        assert "calendar_gap_over_4_days" in flags

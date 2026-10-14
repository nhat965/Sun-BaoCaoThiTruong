import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_DATA_MODE", "fixture")

from sqlalchemy import select

from app.authorized_market_data import import_authorized_prices, preview_authorized_prices
from app.database import PriceObservation, SessionLocal, init_db
from app.registry import import_securities_csv

CSV = """symbol,trading_date,market_timestamp,open,high,low,close,volume,actual_trading_value,market_cap,provider,provider_id,retrieved_at,source_url,adjusted,validation_status
AUTH,2026-10-12,2026-10-12T14:45:00+07:00,100,102,99,101,100000,,,authorized_file,authorized_file,2026-10-13T01:00:00+00:00,https://authorized.example/export.csv,false,valid
"""


def test_preview_is_read_only_and_keeps_missing_value_null():
    result = preview_authorized_prices(CSV, "operator-export")
    assert result.validation_status == "valid"
    assert result.rejected == 0
    assert result.symbols == ["AUTH"]


def test_import_is_idempotent_and_does_not_derive_trading_value():
    init_db()
    import_securities_csv("symbol,name,exchange\nAUTH,Authorized Test,HOSE\n", "test")
    first = import_authorized_prices(CSV, "operator-export")
    second = import_authorized_prices(CSV, "operator-export")
    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped == 1
    with SessionLocal() as session:
        row = session.scalar(
            select(PriceObservation).where(PriceObservation.provider_id == "authorized_file")
        )
        assert row is not None
        assert row.actual_trading_value is None
        assert row.source_mode == "authorized"
        assert row.source_url == "https://authorized.example/export.csv"


def test_session_date_mismatch_is_rejected():
    invalid = CSV.replace("2026-10-12,2026-10-12T14:45:00+07:00", "2026-10-11,2026-10-12T14:45:00+07:00")
    result = preview_authorized_prices(invalid, "operator-export")
    assert result.validation_status == "rejected"
    assert result.rejected == 1
    assert "does not match" in result.errors[0]

import os
from datetime import UTC, datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.analytics.fundamental import calculate_financial_metrics
from app.auth import admin_rate_limiter
from app.config import Settings, get_settings
from app.database import (
    FinancialPeriodRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
    init_db,
)
from app.main import app
from app.registry import seed_registry_if_empty
from app.repositories import FinancialRepository, PriceRepository
from app.schemas import FinancialInputs, PriceBar, PriceSeries, Provenance
from app.securities_explorer import list_securities


@pytest.fixture(scope="module", autouse=True)
def _database():
    init_db()
    seed_registry_if_empty()
    yield
    with SessionLocal() as session:
        session.execute(
            delete(PriceObservation).where(PriceObservation.provider_id == "yahoo")
        )
        session.commit()


def _series(source: str, bars: list[PriceBar], *, mode: str = "live") -> PriceSeries:
    with SessionLocal() as session:
        security = session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == "HPG")
        )
        assert security is not None
        from app.repositories import security_schema

        schema = security_schema(security)
    return PriceSeries(
        security=schema,
        interval="1d",
        adjusted=False,
        bars=bars,
        provenance=Provenance(
            source=source,
            provider_symbol="HPG.TEST",
            retrieved_at=datetime(2026, 1, 3, 8, tzinfo=UTC),
            market_timestamp=bars[-1].timestamp,
            mode=mode,
            delayed=True,
            validation_status="valid",
        ),
    )


def _bar(day: int, close: float, *, hour: int = 2) -> PriceBar:
    return PriceBar(
        timestamp=datetime(2026, 1, day, hour, tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000,
    )


def test_price_replay_and_same_session_are_idempotent():
    first_series = _series("Yahoo Finance chart", [_bar(2, 100)])
    replay_series = _series("Yahoo Finance chart", [_bar(2, 100)])
    corrected_series = _series("Yahoo Finance chart", [_bar(2, 101, hour=3)])
    with SessionLocal() as session:
        security_id = session.scalar(
            select(SecurityRecord.id).where(SecurityRecord.symbol == "HPG")
        )
        session.execute(
            delete(PriceObservation).where(PriceObservation.security_id == security_id)
        )
        session.commit()

        repository = PriceRepository(session)
        first = repository.upsert_series_with_counts(first_series)
        replay = repository.upsert_series_with_counts(replay_series)
        corrected = repository.upsert_series_with_counts(corrected_series)
        session.commit()

        count = session.scalar(
            select(func.count(PriceObservation.id)).where(
                PriceObservation.security_id == security_id
            )
        )

    assert first.inserted == 1
    assert replay.updated == 0
    assert replay.skipped == 1
    assert corrected.updated == 1
    assert count == 1


def test_explorer_uses_distinct_sessions_and_trusted_provider():
    yahoo = _series("Yahoo Finance chart", [_bar(2, 100), _bar(3, 110)])
    fixture = _series(
        "Synthetic fixture (development only)",
        [_bar(3, 999, hour=4)],
        mode="fixture",
    )
    with SessionLocal() as session:
        security_id = session.scalar(
            select(SecurityRecord.id).where(SecurityRecord.symbol == "HPG")
        )
        session.execute(
            delete(PriceObservation).where(PriceObservation.security_id == security_id)
        )
        repository = PriceRepository(session)
        repository.upsert_series_with_counts(yahoo)
        repository.upsert_series_with_counts(fixture)
        session.commit()

    result = list_securities(page=1, page_size=20, query="HPG")
    item = result.items[0]
    assert item.latest_price == 110
    assert item.change_percent == 10
    assert item.price_source == "Yahoo Finance chart"


def test_identical_financial_replay_is_skipped_and_versions_are_preserved():
    header = (
        "period_end,period_type,fiscal_year,statement_type,item_code,value,unit,"
        "verification_status,statement_scope,statement_status,source_url\n"
    )
    original = header + (
        "2040-12-31T00:00:00+00:00,year,2040,income,revenue,100,MILLION_VND,"
        "verified,consolidated,original,https://example.com/original\n"
    )
    amended = header + (
        "2040-12-31T00:00:00+00:00,year,2040,income,revenue,110,MILLION_VND,"
        "verified,consolidated,amended,https://example.com/amended\n"
    )
    with SessionLocal() as session:
        repository = FinancialRepository(session)
        first = repository.import_csv("HPG", original, "authorized-test")
        replay = repository.import_csv("HPG", original, "authorized-test")
        repository.import_csv("HPG", amended, "authorized-test")
        statements = repository.statements(
            "HPG", period_type="year", statement_scope="consolidated"
        )

    assert first.inserted_items == 1
    assert replay.updated_items == 0
    assert replay.skipped_items == 1
    versions = {
        (period.statement_status, period.items[0].value)
        for period in statements.periods
        if period.period_end.year == 2040
    }
    assert versions == {("original", 100_000_000), ("amended", 110_000_000)}


def test_strict_financial_validation_rolls_back_invalid_period_and_keeps_report():
    content = (
        "period_end,period_type,fiscal_year,statement_type,item_code,value,unit,"
        "statement_scope,statement_status,source_url\n"
        "2041-12-31T00:00:00+00:00,year,2041,balance,total_assets,100,VND,"
        "consolidated,original,https://example.com/invalid\n"
        "2041-12-31T00:00:00+00:00,year,2041,balance,total_liabilities,20,VND,"
        "consolidated,original,https://example.com/invalid\n"
        "2041-12-31T00:00:00+00:00,year,2041,balance,total_equity,60,VND,"
        "consolidated,original,https://example.com/invalid\n"
    )
    with SessionLocal() as session:
        result = FinancialRepository(session).import_csv(
            "HPG", content, "authorized-test", strict=True
        )
        assert result.rejected > 0
        assert result.validation_reports[0].validation_status == "invalid"
        assert any(
            issue.code == "balance_equation_mismatch"
            for issue in result.validation_reports[0].issues
        )
        assert not session.scalar(
            select(FinancialPeriodRecord).where(
                FinancialPeriodRecord.period_end == datetime(2041, 12, 31, tzinfo=UTC)
            )
        )


def test_roic_uses_nopat_and_average_invested_capital():
    result = calculate_financial_metrics(
        FinancialInputs(
            entity_type="non_financial",
            operating_income=20,
            profit_before_tax=25,
            tax_expense=5,
            total_debt=40,
            total_equity=80,
            cash_and_equivalents=10,
            prior_total_debt=30,
            prior_total_equity=70,
            prior_cash_and_equivalents=8,
        )
    )
    assert result.metrics["roic_percent"] == 15.841584


def test_bank_does_not_use_non_financial_roic_or_current_ratio():
    result = calculate_financial_metrics(
        FinancialInputs(
            entity_type="bank",
            operating_income=20,
            profit_before_tax=25,
            tax_expense=5,
            total_debt=40,
            total_equity=80,
            cash_and_equivalents=10,
            current_assets=100,
            current_liabilities=50,
        )
    )
    assert result.metrics["roic_percent"] is None
    assert result.metrics["current_ratio"] is None
    assert any("ngân hàng" in warning.lower() for warning in result.warnings)


def test_financial_https_sync_blocks_private_ip_before_request(monkeypatch):
    import httpx

    def unexpected_request(self, url, **kwargs):
        raise AssertionError("private destination must be rejected before HTTP")

    monkeypatch.setattr(httpx.Client, "get", unexpected_request)
    token = "data-integrity-admin-token-long-enough"
    app.dependency_overrides[get_settings] = lambda: Settings(
        market_data_mode="fixture",
        admin_api_token=token,
        admin_rate_limit_per_minute=1000,
        financial_csv_url_template="https://127.0.0.1/{symbol}.csv",
        financial_csv_allowed_hosts="127.0.0.1",
        financial_csv_rights_confirmed=True,
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/sync/financials/HPG",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "BLOCKED"
    finally:
        app.dependency_overrides.clear()
        admin_rate_limiter.reset()

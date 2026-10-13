from datetime import UTC, datetime
from decimal import Decimal

from app.financial_validation import validate_period


def _metadata():
    return {
        "period_type": "year",
        "period_start": datetime(2025, 1, 1, tzinfo=UTC),
        "period_end": datetime(2025, 12, 31, tzinfo=UTC),
        "reported_at": datetime(2026, 2, 1, tzinfo=UTC),
        "currency": "VND",
        "statement_scope": "consolidated",
        "statement_status": "original",
        "source_name": "authorized-test",
        "source_url": "https://example.com/report",
    }


def test_validation_reconciles_balance_and_income_relationships():
    result = validate_period(
        **_metadata(),
        values={
            "total_assets": Decimal(100),
            "total_liabilities": Decimal(40),
            "total_equity": Decimal(60),
            "revenue": Decimal(120),
            "cost_of_goods_sold": Decimal(70),
            "gross_profit": Decimal(50),
        },
    )
    assert result.status == "valid"
    assert "balance_sheet_equation" in result.checks
    assert "income_statement_relationships" in result.checks


def test_validation_reports_accounting_mismatch_and_missing_data():
    result = validate_period(
        **_metadata(),
        values={
            "total_assets": Decimal(100),
            "total_liabilities": Decimal(20),
            "total_equity": Decimal(60),
            "revenue": Decimal(120),
            "cost_of_goods_sold": Decimal(70),
            "gross_profit": Decimal(70),
        },
    )
    assert result.status == "invalid"
    assert {issue.code for issue in result.issues} >= {
        "balance_equation_mismatch",
        "gross_profit_mismatch",
    }


def test_validation_rejects_non_finite_values_without_coercing_to_zero():
    result = validate_period(
        **_metadata(),
        values={"revenue": Decimal("NaN")},
    )
    assert result.status == "invalid"
    assert any(issue.code == "non_finite_value" for issue in result.issues)

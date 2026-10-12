from app.analytics.fundamental import calculate_financial_metrics, growth
from app.schemas import FinancialInputs


def test_growth_and_core_ratios():
    result = calculate_financial_metrics(
        FinancialInputs(
            revenue=120,
            prior_revenue=100,
            net_income=12,
            prior_net_income=10,
            total_assets=200,
            total_equity=80,
            total_debt=40,
            current_assets=60,
            current_liabilities=30,
            operating_income=20,
            interest_expense=4,
            operating_cash_flow=18,
            capital_expenditure=5,
            shares_outstanding=10,
            market_price=24,
        )
    )
    assert growth(120, 100) == 20
    assert result.metrics["roe_percent"] == 15
    assert result.metrics["current_ratio"] == 2
    assert result.metrics["free_cash_flow"] == 13
    assert result.metrics["pe"] == 20


def test_negative_earnings_make_pe_unavailable():
    result = calculate_financial_metrics(
        FinancialInputs(net_income=-10, shares_outstanding=5, market_price=20)
    )
    assert result.metrics["pe"] is None
    assert any("Lợi nhuận âm" in warning for warning in result.warnings)

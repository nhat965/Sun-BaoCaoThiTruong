from app.analytics.formula_registry import FORMULA_VERSION, get_formula_definition
from app.analytics.fundamental import calculate_financial_metrics
from app.schemas import FinancialInputs


def test_capex_sign_is_normalized_and_metadata_is_versioned():
    result = calculate_financial_metrics(
        FinancialInputs(
            revenue=200,
            net_income=40,
            operating_cash_flow=100,
            capital_expenditure=-40,
            total_debt=80,
            cash_and_equivalents=20,
            current_assets=120,
            inventory=20,
            current_liabilities=50,
            shares_outstanding=10,
        )
    )

    assert result.metrics["free_cash_flow"] == 60
    assert result.metrics["quick_ratio"] == 2
    assert result.metrics["net_debt"] == 60
    assert result.metrics["cash_conversion_percent"] == 250
    assert result.metrics["capex_intensity_percent"] == 20
    assert result.formula_version == FORMULA_VERSION
    assert result.metric_metadata["free_cash_flow"].formula_version == FORMULA_VERSION
    assert result.metric_metadata["free_cash_flow"].input_status == "complete"


def test_eps_prefers_parent_profit_and_diluted_shares():
    result = calculate_financial_metrics(
        FinancialInputs(
            net_income=100,
            net_income_attributable_to_parent=80,
            shares_outstanding=10,
            diluted_shares_outstanding=20,
        )
    )

    assert result.metrics["eps"] == 4
    assert result.metric_metadata["eps"].input_status == "complete"


def test_metadata_exposes_missing_inputs_and_not_applicable_metrics():
    incomplete = calculate_financial_metrics(FinancialInputs(revenue=100))
    assert "prior_revenue" in incomplete.metric_metadata["revenue_growth_percent"].missing_inputs
    assert incomplete.metric_metadata["revenue_growth_percent"].input_status == "incomplete"

    bank = calculate_financial_metrics(FinancialInputs(entity_type="bank", revenue=100))
    assert bank.metric_metadata["gross_margin_percent"].input_status == "not_applicable"


def test_formula_registry_returns_a_stable_definition():
    definition = get_formula_definition("roic_percent")
    assert definition is not None
    assert "NOPAT" in definition.formula_description

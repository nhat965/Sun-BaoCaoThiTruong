"""Versioned financial metric definitions and input provenance metadata."""

from dataclasses import dataclass

FORMULA_VERSION = "fundamental-v3"


@dataclass(frozen=True)
class FormulaDefinition:
    metric_code: str
    required_inputs: tuple[str, ...]
    applicable_company_types: tuple[str, ...]
    period_policy: str
    unit: str
    formula_description: str
    limitations: str


_COMMON = ("non_financial", "bank", "securities", "insurance")
_NON_FINANCIAL = ("non_financial",)

FORMULA_REGISTRY: dict[str, FormulaDefinition] = {
    "revenue_growth_percent": FormulaDefinition(
        "revenue_growth_percent", ("revenue", "prior_revenue"), _COMMON, "same_period_yoy", "%",
        "(current - prior) / prior × 100", "Null when the comparison base is not positive.",
    ),
    "revenue_qoq_percent": FormulaDefinition(
        "revenue_qoq_percent", ("revenue", "previous_period_revenue"), _COMMON, "previous_period", "%",
        "(current - previous period) / previous period × 100", "Quarter/YTD comparability is caller-provided.",
    ),
    "net_income_growth_percent": FormulaDefinition(
        "net_income_growth_percent", ("net_income", "prior_net_income"), _COMMON, "same_period_yoy", "%",
        "(current - prior) / prior × 100", "Null when the comparison base is not positive.",
    ),
    "gross_margin_percent": FormulaDefinition(
        "gross_margin_percent", ("gross_profit", "revenue"), _NON_FINANCIAL, "period", "%",
        "gross profit / revenue × 100", "Not applicable to banks and other financial entities.",
    ),
    "roe_percent": FormulaDefinition(
        "roe_percent", ("net_income", "total_equity"), _NON_FINANCIAL, "average_balance", "%",
        "net income / average equity × 100", "Uses current equity when a prior balance is unavailable.",
    ),
    "roa_percent": FormulaDefinition(
        "roa_percent", ("net_income", "total_assets"), _NON_FINANCIAL, "average_balance", "%",
        "net income / average assets × 100", "Uses current assets when a prior balance is unavailable.",
    ),
    "roic_percent": FormulaDefinition(
        "roic_percent", ("operating_income", "profit_before_tax", "tax_expense", "total_debt", "total_equity", "cash_and_equivalents"), _NON_FINANCIAL, "average_balance", "%",
        "NOPAT / average(debt + equity - cash) × 100", "Requires a defensible tax rate and invested-capital inputs.",
    ),
    "eps": FormulaDefinition(
        "eps", ("net_income", "shares_outstanding"), _COMMON, "period", "VND/share",
        "parent-attributable net income (or total net income fallback) / weighted shares", "Diluted shares are preferred when supplied; otherwise basic shares are used.",
    ),
    "free_cash_flow": FormulaDefinition(
        "free_cash_flow", ("operating_cash_flow", "capital_expenditure"), _NON_FINANCIAL, "period", "currency",
        "operating cash flow - normalized CAPEX", "CAPEX sign is normalized before subtraction.",
    ),
    "quick_ratio": FormulaDefinition(
        "quick_ratio", ("current_assets", "inventory", "current_liabilities"), _NON_FINANCIAL, "period", "ratio",
        "(current assets - inventory) / current liabilities", "Not applicable to banks and other financial entities.",
    ),
    "operating_cash_flow_to_net_income": FormulaDefinition(
        "operating_cash_flow_to_net_income", ("operating_cash_flow", "net_income"), _COMMON, "period", "ratio",
        "operating cash flow / net income", "Interpret with care when net income is zero or negative.",
    ),
    "net_debt": FormulaDefinition(
        "net_debt", ("total_debt", "cash_and_equivalents"), _COMMON, "period", "currency",
        "total debt - cash and equivalents", "Null when either balance is unavailable.",
    ),
    "cash_to_debt": FormulaDefinition(
        "cash_to_debt", ("cash_and_equivalents", "total_debt"), _COMMON, "period", "ratio",
        "cash and equivalents / total debt", "Null when debt is zero or unavailable.",
    ),
    "debt_to_ebitda": FormulaDefinition(
        "debt_to_ebitda", ("total_debt", "ebitda"), _NON_FINANCIAL, "period", "ratio",
        "total debt / EBITDA", "Leverage proxy; not meaningful when EBITDA is non-positive.",
    ),
    "cash_conversion_percent": FormulaDefinition(
        "cash_conversion_percent", ("operating_cash_flow", "net_income"), _COMMON, "period", "%",
        "operating cash flow / net income × 100", "Interpret with care when net income is zero or negative.",
    ),
    "capex_intensity_percent": FormulaDefinition(
        "capex_intensity_percent", ("capital_expenditure", "revenue"), _NON_FINANCIAL, "period", "%",
        "normalized CAPEX / revenue × 100", "CAPEX sign is normalized before calculation.",
    ),
}


def get_formula_definition(metric_code: str) -> FormulaDefinition | None:
    return FORMULA_REGISTRY.get(metric_code)


def formula_registry() -> dict[str, FormulaDefinition]:
    return dict(FORMULA_REGISTRY)

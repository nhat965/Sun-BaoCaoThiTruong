from datetime import UTC, datetime

from app.schemas import FinancialInputs, FinancialMetricResult


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def growth(current: float | None, previous: float | None) -> float | None:
    value = safe_divide(
        None if current is None or previous is None else current - previous, previous
    )
    return None if value is None else value * 100


def calculate_financial_metrics(inputs: FinancialInputs) -> FinancialMetricResult:
    earnings_per_share = safe_divide(inputs.net_income, inputs.shares_outstanding)
    book_value_per_share = safe_divide(inputs.total_equity, inputs.shares_outstanding)
    free_cash_flow = (
        None
        if inputs.operating_cash_flow is None or inputs.capital_expenditure is None
        else inputs.operating_cash_flow - inputs.capital_expenditure
    )
    metrics = {
        "revenue_growth_percent": growth(inputs.revenue, inputs.prior_revenue),
        "net_income_growth_percent": growth(inputs.net_income, inputs.prior_net_income),
        "roe_percent": None
        if (value := safe_divide(inputs.net_income, inputs.total_equity)) is None
        else value * 100,
        "roa_percent": None
        if (value := safe_divide(inputs.net_income, inputs.total_assets)) is None
        else value * 100,
        "net_margin_percent": None
        if (value := safe_divide(inputs.net_income, inputs.revenue)) is None
        else value * 100,
        "debt_to_equity": safe_divide(inputs.total_debt, inputs.total_equity),
        "current_ratio": safe_divide(inputs.current_assets, inputs.current_liabilities),
        "interest_coverage": safe_divide(inputs.operating_income, inputs.interest_expense),
        "free_cash_flow": free_cash_flow,
        "eps": earnings_per_share,
        "book_value_per_share": book_value_per_share,
        "pe": safe_divide(inputs.market_price, earnings_per_share),
        "pb": safe_divide(inputs.market_price, book_value_per_share),
    }
    rounded = {key: None if value is None else round(value, 6) for key, value in metrics.items()}
    warnings = []
    if inputs.net_income is not None and inputs.net_income < 0:
        warnings.append("Lợi nhuận âm làm P/E không có ý nghĩa kinh tế thông thường.")
        rounded["pe"] = None
    if inputs.total_equity is not None and inputs.total_equity <= 0:
        warnings.append(
            "Vốn chủ sở hữu không dương; ROE, D/E và P/B cần được diễn giải thận trọng."
        )
    missing = sum(value is None for value in rounded.values())
    if missing:
        warnings.append(
            f"{missing}/{len(rounded)} chỉ tiêu không tính được do thiếu hoặc mẫu số bằng 0."
        )
    return FinancialMetricResult(
        metrics=rounded, calculated_at=datetime.now(UTC), warnings=warnings
    )

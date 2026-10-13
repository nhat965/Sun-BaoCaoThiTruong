from datetime import UTC, datetime

from app.schemas import FinancialInputs, FinancialMetricResult


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def growth(current: float | None, previous: float | None) -> float | None:
    if previous is None or previous <= 0:
        return None
    value = safe_divide(
        None if current is None or previous is None else current - previous, previous
    )
    return None if value is None else value * 100


def calculate_financial_metrics(inputs: FinancialInputs) -> FinancialMetricResult:
    earnings_per_share = safe_divide(inputs.net_income, inputs.shares_outstanding)
    book_value_per_share = safe_divide(inputs.total_equity, inputs.shares_outstanding)
    average_equity = (
        (inputs.total_equity + inputs.prior_total_equity) / 2
        if inputs.total_equity is not None and inputs.prior_total_equity is not None
        else inputs.total_equity
    )
    average_assets = (
        (inputs.total_assets + inputs.prior_total_assets) / 2
        if inputs.total_assets is not None and inputs.prior_total_assets is not None
        else inputs.total_assets
    )
    free_cash_flow = (
        None
        if inputs.operating_cash_flow is None or inputs.capital_expenditure is None
        else inputs.operating_cash_flow - inputs.capital_expenditure
    )
    ttm_free_cash_flow = (
        None
        if inputs.ttm_operating_cash_flow is None
        or inputs.ttm_capital_expenditure is None
        else inputs.ttm_operating_cash_flow - inputs.ttm_capital_expenditure
    )
    annualization_factor = 12 / inputs.period_months if inputs.period_months else None
    warnings = []
    is_financial = inputs.entity_type in {"bank", "securities", "insurance"}
    tax_rate = safe_divide(inputs.tax_expense, inputs.profit_before_tax)
    if tax_rate is not None and not 0 <= tax_rate <= 1:
        warnings.append("Thuế suất hiệu dụng nằm ngoài 0-100%; ROIC được để trống.")
        tax_rate = None
    nopat = (
        inputs.operating_income * (1 - tax_rate)
        if inputs.operating_income is not None and tax_rate is not None
        else None
    )

    def invested_capital(
        debt: float | None, equity: float | None, cash: float | None
    ) -> float | None:
        if debt is None or equity is None or cash is None:
            return None
        value = debt + equity - cash
        return value if value > 0 else None

    current_invested_capital = invested_capital(
        inputs.total_debt, inputs.total_equity, inputs.cash_and_equivalents
    )
    prior_invested_capital = invested_capital(
        inputs.prior_total_debt,
        inputs.prior_total_equity,
        inputs.prior_cash_and_equivalents,
    )
    average_invested_capital = (
        (current_invested_capital + prior_invested_capital) / 2
        if current_invested_capital is not None
        and prior_invested_capital is not None
        else current_invested_capital
    )
    roic = None if is_financial else safe_divide(nopat, average_invested_capital)
    if is_financial:
        warnings.append(
            "ROIC, current ratio và D/E kiểu doanh nghiệp phi tài chính không áp dụng "
            "máy móc cho ngân hàng/chứng khoán/bảo hiểm."
        )
    elif roic is None:
        warnings.append(
            "ROIC chưa tính được: cần EBIT, lợi nhuận trước thuế, thuế, nợ, vốn chủ "
            "sở hữu và tiền mặt để tính NOPAT/vốn đầu tư."
        )
    if inputs.period_months and inputs.period_months < 12:
        warnings.append(
            "Annualization chỉ nhân tuyến tính theo số tháng của kỳ; không phải dự báo TTM."
        )
    if any(
        value is not None and value <= 0
        for value in (
            inputs.prior_revenue,
            inputs.prior_net_income,
            inputs.previous_period_revenue,
            inputs.previous_period_net_income,
        )
    ):
        warnings.append(
            "Tăng trưởng YoY/QoQ được để trống khi kỳ gốc không dương để tránh tỷ lệ gây hiểu lầm."
        )
    metrics = {
        "revenue_growth_percent": growth(inputs.revenue, inputs.prior_revenue),
        "net_income_growth_percent": growth(inputs.net_income, inputs.prior_net_income),
        "revenue_yoy_percent": growth(inputs.revenue, inputs.prior_revenue),
        "net_income_yoy_percent": growth(inputs.net_income, inputs.prior_net_income),
        "revenue_qoq_percent": growth(inputs.revenue, inputs.previous_period_revenue),
        "net_income_qoq_percent": growth(
            inputs.net_income, inputs.previous_period_net_income
        ),
        "ttm_revenue": inputs.ttm_revenue,
        "ttm_net_income": inputs.ttm_net_income,
        "annualized_revenue": (
            inputs.revenue * annualization_factor
            if inputs.revenue is not None and annualization_factor is not None
            else None
        ),
        "annualized_net_income": (
            inputs.net_income * annualization_factor
            if inputs.net_income is not None and annualization_factor is not None
            else None
        ),
        "roe_percent": None
        if average_equity is None
        or average_equity <= 0
        or (value := safe_divide(inputs.net_income, average_equity)) is None
        else value * 100,
        "roa_percent": None
        if average_assets is None
        or average_assets <= 0
        or (value := safe_divide(inputs.net_income, average_assets)) is None
        else value * 100,
        "roic_percent": None if roic is None else roic * 100,
        "gross_margin_percent": None
        if (value := safe_divide(inputs.gross_profit, inputs.revenue)) is None
        else value * 100,
        "operating_margin_percent": None
        if (value := safe_divide(inputs.operating_income, inputs.revenue)) is None
        else value * 100,
        "net_margin_percent": None
        if (value := safe_divide(inputs.net_income, inputs.revenue)) is None
        else value * 100,
        "debt_to_equity": None
        if is_financial or inputs.total_equity is None or inputs.total_equity <= 0
        else safe_divide(inputs.total_debt, inputs.total_equity),
        "current_ratio": None
        if is_financial
        or inputs.current_liabilities is None
        or inputs.current_liabilities <= 0
        else safe_divide(inputs.current_assets, inputs.current_liabilities),
        "interest_coverage": None
        if inputs.interest_expense is None or inputs.interest_expense <= 0
        else safe_divide(inputs.operating_income, inputs.interest_expense),
        "free_cash_flow": free_cash_flow,
        "ttm_free_cash_flow": ttm_free_cash_flow,
        "eps": earnings_per_share,
        "book_value_per_share": book_value_per_share,
        "pe": safe_divide(inputs.market_price, earnings_per_share),
        "pb": safe_divide(inputs.market_price, book_value_per_share),
        "ps": safe_divide(
            inputs.market_price,
            safe_divide(inputs.revenue, inputs.shares_outstanding),
        ),
        "ev_to_ebitda": safe_divide(inputs.enterprise_value, inputs.ebitda),
        "operating_cash_flow": inputs.operating_cash_flow,
    }
    rounded = {key: None if value is None else round(value, 6) for key, value in metrics.items()}
    if inputs.net_income is not None and inputs.net_income <= 0:
        warnings.append("Lợi nhuận âm hoặc bằng 0 làm P/E không có ý nghĩa kinh tế thông thường.")
        rounded["pe"] = None
    if inputs.total_equity is not None and inputs.total_equity <= 0:
        rounded["pb"] = None
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
        metrics=rounded,
        calculated_at=datetime.now(UTC),
        formula_version="fundamental-v2",
        warnings=warnings,
    )

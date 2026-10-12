from datetime import UTC, datetime

from app.schemas import (
    DCFRequest,
    DCFSensitivityRequest,
    DCFSensitivityResult,
    ValuationRequest,
    ValuationResult,
)


def calculate_relative_valuation(request: ValuationRequest) -> ValuationResult:
    """Calculate a transparent relative valuation from explicitly supplied assumptions."""
    pe_value = request.eps * request.pe_multiple
    pb_value = request.bvps * request.pb_multiple
    base = (pe_value + pb_value) / 2
    multipliers = {
        "bull": request.bull_multiplier,
        "base": request.base_multiplier,
        "bear": request.bear_multiplier,
    }
    return ValuationResult(
        symbol=request.symbol.strip().upper(),
        scenarios={name: round(base * multiplier, 4) for name, multiplier in multipliers.items()},
        assumptions={
            "eps": request.eps,
            "bvps": request.bvps,
            "pe_multiple": request.pe_multiple,
            "pb_multiple": request.pb_multiple,
            "bull_multiplier": request.bull_multiplier,
            "base_multiplier": request.base_multiplier,
            "bear_multiplier": request.bear_multiplier,
            "assumption_source": request.assumption_source,
        },
        warnings=[
            "Đây là định giá tương đối dựa trên giả định người dùng cung cấp; không phải dữ liệu dự báo live.",
            "Chưa có peer set hoặc dải P/E-P/B lịch sử được xác minh trong hệ thống.",
        ],
        calculated_at=datetime.now(UTC),
    )


def calculate_dcf_valuation(request: DCFRequest) -> ValuationResult:
    """Discount explicit user-supplied FCF forecasts and a Gordon-growth terminal value."""
    present_value = sum(
        cash_flow / ((1 + request.discount_rate) ** year)
        for year, cash_flow in enumerate(request.forecast_free_cash_flows, start=1)
    )
    last_cash_flow = request.forecast_free_cash_flows[-1]
    terminal_value = (
        last_cash_flow
        * (1 + request.terminal_growth_rate)
        / (request.discount_rate - request.terminal_growth_rate)
    )
    discounted_terminal = terminal_value / (
        (1 + request.discount_rate) ** len(request.forecast_free_cash_flows)
    )
    enterprise_value = present_value + discounted_terminal
    equity_value = enterprise_value - request.net_debt
    base_per_share = equity_value / request.shares_outstanding
    return ValuationResult(
        symbol=request.symbol.strip().upper(),
        method="dcf-fcf",
        scenarios={
            "bull": round(base_per_share * request.bull_multiplier, 4),
            "base": round(base_per_share, 4),
            "bear": round(base_per_share * request.bear_multiplier, 4),
        },
        assumptions={
            "forecast_free_cash_flows": request.forecast_free_cash_flows,
            "discount_rate": request.discount_rate,
            "terminal_growth_rate": request.terminal_growth_rate,
            "net_debt": request.net_debt,
            "shares_outstanding": request.shares_outstanding,
            "bull_multiplier": request.bull_multiplier,
            "bear_multiplier": request.bear_multiplier,
            "assumption_source": request.assumption_source,
        },
        warnings=[
            "DCF chỉ phù hợp khi dòng tiền tự do có thể dự báo hợp lý; không nên áp dụng máy móc cho mọi doanh nghiệp.",
            "Toàn bộ dự báo và tỷ lệ chiết khấu là giả định do người dùng cung cấp, không phải dữ liệu quan sát.",
        ],
        calculated_at=datetime.now(UTC),
    )


def calculate_dcf_sensitivity(request: DCFSensitivityRequest) -> DCFSensitivityResult:
    """Calculate a DCF matrix entirely from explicit user assumptions."""
    values = {}
    invalid_cells = 0
    for discount_rate in request.discount_rates:
        row = {}
        for growth_rate in request.terminal_growth_rates:
            key = f"{growth_rate:.6g}"
            if growth_rate >= discount_rate:
                row[key] = None
                invalid_cells += 1
                continue
            present_value = sum(
                cash_flow / ((1 + discount_rate) ** year)
                for year, cash_flow in enumerate(
                    request.forecast_free_cash_flows, start=1
                )
            )
            terminal_value = (
                request.forecast_free_cash_flows[-1]
                * (1 + growth_rate)
                / (discount_rate - growth_rate)
            )
            enterprise_value = present_value + terminal_value / (
                (1 + discount_rate) ** len(request.forecast_free_cash_flows)
            )
            row[key] = round(
                (enterprise_value - request.net_debt) / request.shares_outstanding,
                4,
            )
        values[f"{discount_rate:.6g}"] = row
    warnings = [
        "Ma trận chỉ dùng giả định người dùng cung cấp; không phải dự báo hoặc khuyến nghị."
    ]
    if invalid_cells:
        warnings.append(
            f"{invalid_cells} ô không khả dụng vì tăng trưởng dài hạn không thấp hơn tỷ lệ chiết khấu."
        )
    return DCFSensitivityResult(
        symbol=request.symbol.strip().upper(),
        discount_rates=request.discount_rates,
        terminal_growth_rates=request.terminal_growth_rates,
        values=values,
        assumptions={
            "forecast_free_cash_flows": request.forecast_free_cash_flows,
            "net_debt": request.net_debt,
            "shares_outstanding": request.shares_outstanding,
            "assumption_source": request.assumption_source,
        },
        warnings=warnings,
        calculated_at=datetime.now(UTC),
    )

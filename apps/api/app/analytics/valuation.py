from datetime import UTC, datetime

from app.schemas import ValuationRequest, ValuationResult


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

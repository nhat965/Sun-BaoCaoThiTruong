from datetime import UTC

from app.connectors.base import ConnectorError
from app.schemas import PriceBar, PriceSeries


def validate_bar(bar: PriceBar) -> list[str]:
    errors = []
    if min(bar.open, bar.high, bar.low, bar.close) < 0:
        errors.append("negative price")
    if bar.volume < 0:
        errors.append("negative volume")
    if bar.high < max(bar.open, bar.close, bar.low):
        errors.append("high is below OHLC value")
    if bar.low > min(bar.open, bar.close, bar.high):
        errors.append("low is above OHLC value")
    if bar.timestamp.tzinfo is None:
        errors.append("naive timestamp")
    return errors


def normalize_price_series(series: PriceSeries) -> PriceSeries:
    normalized: dict[str, PriceBar] = {}
    invalid: list[str] = []
    for bar in series.bars:
        errors = validate_bar(bar)
        if errors:
            invalid.append(f"{bar.timestamp.isoformat()}: {', '.join(errors)}")
            continue
        timestamp = bar.timestamp.astimezone(UTC)
        normalized[timestamp.isoformat()] = bar.model_copy(update={"timestamp": timestamp})
    if invalid:
        raise ConnectorError(
            f"Nguồn trả {len(invalid)} OHLCV không hợp lệ; toàn bộ chuỗi bị từ chối. "
            f"Mẫu lỗi: {invalid[0]}"
        )
    bars = sorted(normalized.values(), key=lambda item: item.timestamp)
    if not bars:
        raise ConnectorError("Chuỗi giá không có quan sát hợp lệ sau chuẩn hóa.")
    provenance = series.provenance.model_copy(
        update={"market_timestamp": bars[-1].timestamp, "validation_status": "valid"}
    )
    return series.model_copy(update={"bars": bars, "provenance": provenance})

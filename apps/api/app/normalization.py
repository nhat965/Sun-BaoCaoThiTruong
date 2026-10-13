from datetime import UTC
from math import isfinite

from app.connectors.base import ConnectorError
from app.schemas import PriceBar, PriceSeries


def validate_bar(bar: PriceBar) -> list[str]:
    errors = []
    if not all(isfinite(value) for value in (bar.open, bar.high, bar.low, bar.close)):
        errors.append("non-finite price")
    elif min(bar.open, bar.high, bar.low, bar.close) <= 0:
        errors.append("non-positive price")
    if bar.volume < 0:
        errors.append("negative volume")
    if bar.volume > 10**15:
        errors.append("volume is implausibly large")
    if bar.high < max(bar.open, bar.close, bar.low):
        errors.append("high is below OHLC value")
    if bar.low > min(bar.open, bar.close, bar.high):
        errors.append("low is above OHLC value")
    if bar.timestamp.tzinfo is None:
        errors.append("naive timestamp")
    return errors


def normalize_price_series(
    series: PriceSeries, *, allow_empty: bool = False
) -> PriceSeries:
    normalized: dict[str, PriceBar] = {}
    invalid: list[str] = []
    duplicate_count = 0
    conflicting_duplicates = 0
    for bar in series.bars:
        errors = validate_bar(bar)
        if errors:
            invalid.append(f"{bar.timestamp.isoformat()}: {', '.join(errors)}")
            continue
        timestamp = bar.timestamp.astimezone(UTC)
        if timestamp.isoformat() in normalized:
            duplicate_count += 1
            previous = normalized[timestamp.isoformat()]
            if previous.model_dump(exclude={"timestamp"}) != bar.model_dump(
                exclude={"timestamp"}
            ):
                conflicting_duplicates += 1
        normalized[timestamp.isoformat()] = bar.model_copy(update={"timestamp": timestamp})
    if invalid:
        raise ConnectorError(
            f"Nguồn trả {len(invalid)} OHLCV không hợp lệ; toàn bộ chuỗi bị từ chối. "
            f"Mẫu lỗi: {invalid[0]}"
        )
    bars = sorted(normalized.values(), key=lambda item: item.timestamp)
    if not bars and not allow_empty:
        raise ConnectorError("Chuỗi giá không có quan sát hợp lệ sau chuẩn hóa.")
    notes = series.provenance.notes
    if duplicate_count:
        duplicate_note = f"{duplicate_count} duplicate timestamp(s) collapsed during normalization."
        notes = f"{notes}; {duplicate_note}" if notes else duplicate_note
    if conflicting_duplicates:
        conflict_note = (
            f"{conflicting_duplicates} duplicate timestamp(s) had conflicting OHLCV; "
            "the last provider observation was retained."
        )
        notes = f"{notes}; {conflict_note}" if notes else conflict_note
    provenance = series.provenance.model_copy(
        update={
            "market_timestamp": bars[-1].timestamp if bars else series.provenance.market_timestamp,
            "validation_status": "valid",
            "notes": notes,
        }
    )
    return series.model_copy(update={"bars": bars, "provenance": provenance})

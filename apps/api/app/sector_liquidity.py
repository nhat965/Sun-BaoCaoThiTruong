"""Sector and liquidity intelligence derived from canonical daily prices."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import UTC, date, datetime
from statistics import mean

from sqlalchemy import select

from app.database import LiquiditySnapshotRecord, SectorSnapshotRecord, SessionLocal
from app.market_trend import _history, _latest_session
from app.schemas import (
    LiquidityLeader,
    LiquidityResponse,
    SectorIntelligenceResponse,
    SectorMetric,
)

SECTOR_FORMULA_VERSION = "sector-intelligence-v1"
LIQUIDITY_FORMULA_VERSION = "liquidity-intelligence-v1"
TAXONOMY_VERSION = "registry-v1"


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "unclassified"


def _pct(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _average(values: list[float]) -> float | None:
    return _pct(mean(values)) if values else None


def _provenance(rows: list[object]) -> tuple[str, str]:
    modes = {getattr(row, "source_mode", "unknown") for row in rows}
    validations = {getattr(row, "validation_status", "unvalidated") for row in rows}
    mode = next(iter(modes)) if len(modes) == 1 else "historical" if modes else "unavailable"
    validation = "valid" if validations == {"valid"} else "partial" if validations else "unvalidated"
    return mode, validation


def _return(history: list[object], period: int) -> float | None:
    if len(history) <= period or float(history[period].close) == 0:
        return None
    return (float(history[0].close) / float(history[period].close) - 1) * 100


def _relative_volume(history: list[object]) -> float | None:
    if len(history) < 2:
        return None
    baseline = [float(item.volume) for item in history[1:21]]
    if not baseline or mean(baseline) == 0:
        return None
    return float(history[0].volume) / mean(baseline)


def _above_ma(history: list[object], period: int) -> bool | None:
    if len(history) < period:
        return None
    return float(history[0].close) > mean(float(item.close) for item in history[:period])


def _sector_metric(
    sector_id: str,
    sector_name: str,
    securities: list[object],
    by_security: dict[int, list[object]],
    current_date: date,
    index_return_1d: float | None,
) -> SectorMetric:
    members = [item for item in securities if _slug(item.sector or "") == sector_id]
    current_members = [
        item for item in members if by_security.get(item.id) and by_security[item.id][0].market_session_date == current_date
    ]
    returns = {1: [], 5: [], 20: []}
    changes: list[float] = []
    volumes: list[int] = []
    actual_values: list[float] = []
    ma20: list[bool] = []
    ma50: list[bool] = []
    eligible = {1: 0, 5: 0, 20: 0}
    for security in current_members:
        history = by_security[security.id]
        for period, period_returns in returns.items():
            value = _return(history, period)
            if value is not None:
                period_returns.append(value)
                eligible[period] += 1
        if len(history) >= 2:
            change = float(history[0].close) - float(history[1].close)
            changes.append(change)
        volumes.append(int(history[0].volume))
        if history[0].actual_trading_value is not None:
            actual_values.append(float(history[0].actual_trading_value))
        ma20_value = _above_ma(history, 20)
        ma50_value = _above_ma(history, 50)
        if ma20_value is not None:
            ma20.append(ma20_value)
        if ma50_value is not None:
            ma50.append(ma50_value)
    advancers = sum(value > 0 for value in changes)
    decliners = sum(value < 0 for value in changes)
    unchanged = sum(value == 0 for value in changes)
    rs = None
    if index_return_1d is not None and returns[1]:
        sector_return = _average(returns[1])
        rs = sector_return - index_return_1d if sector_return is not None else None
    limitations = []
    if not actual_values:
        limitations.append("Nguồn chưa cung cấp actual_trading_value cho ngành này.")
    if index_return_1d is None:
        limitations.append("Chưa có VN-Index được cấp quyền; relative strength chỉ trả null.")
    return SectorMetric(
        sector_id=sector_id,
        sector_name=sector_name,
        taxonomy_version=TAXONOMY_VERSION,
        stock_count=len(members),
        eligible_1d=eligible[1],
        eligible_5d=eligible[5],
        eligible_20d=eligible[20],
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        performance_1d_percent=_average(returns[1]),
        performance_5d_percent=_average(returns[5]),
        performance_20d_percent=_average(returns[20]),
        volume=sum(volumes) if volumes else None,
        average_volume_5=_average([sum(int(item.volume) for item in by_security[security.id][:5]) / min(5, len(by_security[security.id])) for security in current_members if by_security[security.id]]),
        average_volume_10=_average([sum(int(item.volume) for item in by_security[security.id][:10]) / min(10, len(by_security[security.id])) for security in current_members if by_security[security.id]]),
        average_volume_20=_average([sum(int(item.volume) for item in by_security[security.id][:20]) / min(20, len(by_security[security.id])) for security in current_members if by_security[security.id]]),
        relative_volume=_average([value for security in current_members if (value := _relative_volume(by_security[security.id])) is not None]),
        actual_trading_value=sum(actual_values) if actual_values else None,
        relative_strength_vs_vnindex_percent=rs,
        above_ma20_percent=(sum(ma20) / len(ma20) * 100 if ma20 else None),
        above_ma50_percent=(sum(ma50) / len(ma50) * 100 if ma50 else None),
        coverage={
            "current_session_count": len(current_members),
            "stock_count": len(members),
            "actual_trading_value_count": len(actual_values),
            "ma20_eligible_count": len(ma20),
            "ma50_eligible_count": len(ma50),
        },
        limitations=limitations,
    )


def _index_return_1d(current_date: date) -> float | None:
    from app.database import MarketIndexObservationRecord

    with SessionLocal() as session:
        rows = session.scalars(
            select(MarketIndexObservationRecord)
            .where(
                MarketIndexObservationRecord.symbol == "VNINDEX",
                MarketIndexObservationRecord.market_session_date <= current_date,
            )
            .order_by(
                MarketIndexObservationRecord.market_session_date.desc(),
                MarketIndexObservationRecord.market_timestamp.desc(),
            )
            .limit(2)
        ).all()
    if len(rows) < 2 or rows[1].close == 0:
        return None
    return (float(rows[0].close) / float(rows[1].close) - 1) * 100


def _persist_sector(response: SectorIntelligenceResponse) -> None:
    if response.market_session is None or response.as_of is None:
        return
    now = datetime.now(UTC)
    with SessionLocal() as session:
        for metric in response.sectors:
            existing = session.scalar(
                select(SectorSnapshotRecord).where(
                    SectorSnapshotRecord.sector_id == metric.sector_id,
                    SectorSnapshotRecord.market_session_date == date.fromisoformat(response.market_session),
                    SectorSnapshotRecord.formula_version == response.formula_version,
                )
            )
            values = {
                "sector_id": metric.sector_id,
                "sector_name": metric.sector_name,
                "taxonomy_version": metric.taxonomy_version,
                "market_session_date": date.fromisoformat(response.market_session),
                "as_of": response.as_of,
                "provider": response.source or "canonical-price-selection",
                "data_mode": response.data_mode,
                "validation_status": response.validation_status,
                "coverage_json": json.dumps(metric.coverage, sort_keys=True),
                "metrics_json": metric.model_dump_json(),
                "limitations_json": json.dumps(metric.limitations, ensure_ascii=False),
                "formula_version": response.formula_version,
                "created_at": now,
            }
            if existing is None:
                session.add(SectorSnapshotRecord(**values))
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
        session.commit()


def calculate_sectors(sort_by: str = "performance_1d", sector_filter: str | None = None) -> SectorIntelligenceResponse:
    securities, by_security = _history()
    session_date, as_of, current = _latest_session(securities, by_security)
    source = "canonical-price-selection"
    if session_date is None or as_of is None:
        return SectorIntelligenceResponse(
            source=source,
            warnings=["Chưa có dữ liệu giá hợp lệ để phân tích ngành."],
            limitations=["Không tự gán ngành cho mã thiếu taxonomy từ registry."],
        )
    stocks = list(securities)
    classified = [item for item in stocks if item.sector and item.sector.strip()]
    names = { _slug(item.sector): item.sector.strip() for item in classified }
    if sector_filter:
        normalized = _slug(sector_filter)
        names = {key: value for key, value in names.items() if key == normalized or value.lower() == sector_filter.lower()}
    current_rows = [current[item.id] for item in classified if item.id in current]
    data_mode, validation_status = _provenance(current_rows)
    index_return = _index_return_1d(session_date)
    sectors = [
        _sector_metric(sector_id, name, securities, by_security, session_date, index_return)
        for sector_id, name in sorted(names.items())
    ]
    key_map = {
        "performance": "performance_1d_percent",
        "performance_1d": "performance_1d_percent",
        "performance_5d": "performance_5d_percent",
        "performance_20d": "performance_20d_percent",
        "liquidity": "volume",
        "volume": "volume",
        "breadth": "above_ma20_percent",
        "relative_strength": "relative_strength_vs_vnindex_percent",
    }
    sort_key = key_map.get(sort_by, "performance_1d_percent")
    sectors.sort(key=lambda item: getattr(item, sort_key) is not None, reverse=True)
    sectors.sort(key=lambda item: getattr(item, sort_key) or 0, reverse=True)
    taxonomy_coverage_percent = round(len(classified) / len(securities) * 100, 2) if securities else 0
    current_coverage_percent = round(len(current) / len(securities) * 100, 2) if securities else 0
    response = SectorIntelligenceResponse(
        as_of=as_of,
        market_session=session_date.isoformat(),
        data_status="available" if current_coverage_percent >= 80 else "partial",
        source=source,
        data_mode=data_mode,
        validation_status=validation_status,
        sort_by=sort_key,
        coverage={
            "universe_count": len(securities),
            "current_session_count": len(current),
            "classified_count": len(classified),
            "unclassified_count": len(stocks) - len(classified),
            "taxonomy_coverage_percent": taxonomy_coverage_percent,
            "current_session_coverage_percent": current_coverage_percent,
        },
        sectors=sectors,
        warnings=(
            [f"Taxonomy hiện chỉ phủ {len(classified)}/{len(stocks)} mã trong securities master."]
            if len(classified) < len(stocks)
            else []
        ),
        limitations=[
            "Ngành chỉ lấy từ taxonomy/provenance của securities registry; không tự suy luận từ mã.",
            "Relative strength chỉ được tính khi có VN-Index được cấp quyền.",
            "Thay đổi relative strength và thanh khoản là proxy mô tả, không chứng minh dòng tiền luân chuyển giữa ngành.",
        ],
    )
    _persist_sector(response)
    return response


def _persist_liquidity(response: LiquidityResponse) -> None:
    if response.market_session is None or response.as_of is None:
        return
    now = datetime.now(UTC)
    metrics = response.model_dump(exclude={"as_of", "market_session", "source", "data_mode", "validation_status", "coverage", "warnings", "limitations", "formula_version"})
    with SessionLocal() as session:
        existing = session.scalar(
            select(LiquiditySnapshotRecord).where(
                LiquiditySnapshotRecord.market_session_date == date.fromisoformat(response.market_session),
                LiquiditySnapshotRecord.formula_version == response.formula_version,
            )
        )
        values = {
            "market_session_date": date.fromisoformat(response.market_session),
            "as_of": response.as_of,
            "provider": response.source or "canonical-price-selection",
            "data_mode": response.data_mode,
            "validation_status": response.validation_status,
            "coverage_json": json.dumps(response.coverage, sort_keys=True),
            "metrics_json": json.dumps(metrics, sort_keys=True),
            "limitations_json": json.dumps(response.limitations, ensure_ascii=False),
            "formula_version": response.formula_version,
            "created_at": now,
        }
        if existing is None:
            session.add(LiquiditySnapshotRecord(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.commit()


def calculate_liquidity() -> LiquidityResponse:
    securities, by_security = _history()
    session_date, as_of, current = _latest_session(securities, by_security)
    source = "canonical-price-selection"
    if session_date is None or as_of is None:
        return LiquidityResponse(source=source, warnings=["Chưa có dữ liệu giá hợp lệ để tính thanh khoản."])
    current_stocks = [item for item in securities if item.id in current]
    current_rows = [current[item.id] for item in current_stocks]
    data_mode, validation_status = _provenance(current_rows)
    sessions = sorted({row.market_session_date for values in by_security.values() for row in values}, reverse=True)
    volume_by_session: dict[date, int] = defaultdict(int)
    value_by_session: dict[date, float] = defaultdict(float)
    value_count_by_session: dict[date, int] = defaultdict(int)
    for values in by_security.values():
        for row in values:
            volume_by_session[row.market_session_date] += int(row.volume)
            if row.actual_trading_value is not None:
                value_by_session[row.market_session_date] += float(row.actual_trading_value)
                value_count_by_session[row.market_session_date] += 1
    volume_windows = {period: [volume_by_session[item] for item in sessions[:period] if item in volume_by_session] for period in (5, 10, 20)}
    value_windows = {period: [value_by_session[item] for item in sessions[:period] if value_count_by_session[item] > 0] for period in (5, 10, 20)}
    total_volume = sum(int(row.volume) for row in current_rows)
    values = [float(row.actual_trading_value) for row in current_rows if row.actual_trading_value is not None]
    top_volume = sorted(current_stocks, key=lambda item: int(current[item.id].volume), reverse=True)
    top_value = sorted(
        [item for item in current_stocks if current[item.id].actual_trading_value is not None],
        key=lambda item: float(current[item.id].actual_trading_value),
        reverse=True,
    )
    def share(items: list[object], attr: str, top_n: int) -> float | None:
        amounts = [float(getattr(current[item.id], attr)) for item in items if getattr(current[item.id], attr) is not None]
        if not amounts:
            return None
        return round(sum(amounts[:top_n]) / sum(amounts) * 100, 2) if sum(amounts) else None
    leaders = []
    volume_expansion = decline_heavy = 0
    for security in current_stocks:
        history = by_security[security.id]
        rel = _relative_volume(history)
        ret = _return(history, 1)
        if rel is not None and rel >= 1.5:
            volume_expansion += 1
            if ret is not None and ret <= -2:
                decline_heavy += 1
    for security in top_volume[:10]:
        history = by_security[security.id]
        leaders.append(
            LiquidityLeader(
                symbol=security.symbol,
                sector=security.sector,
                volume=int(history[0].volume),
                actual_trading_value=float(history[0].actual_trading_value) if history[0].actual_trading_value is not None else None,
                return_1d_percent=_return(history, 1),
                relative_volume=_relative_volume(history),
            )
        )
    coverage_percent = round(len(current_stocks) / len(securities) * 100, 2) if securities else 0
    limitations = [
        "Khối lượng không được coi là giá trị giao dịch; actual_trading_value chỉ trả khi provider cung cấp.",
        "Tỷ trọng volume không phải tỷ trọng đóng góp vào VN-Index.",
        "Không có dữ liệu mua/bán ròng khối ngoại được cấp quyền nên foreign_net_value là null.",
    ]
    if not values:
        limitations.append("Chưa có actual_trading_value để tính concentration theo giá trị giao dịch.")
    response = LiquidityResponse(
        as_of=as_of,
        market_session=session_date.isoformat(),
        data_status="available" if coverage_percent >= 80 else "partial",
        source=source,
        data_mode=data_mode,
        validation_status=validation_status,
        coverage={
            "universe_count": len(securities),
            "current_session_count": len(current_stocks),
            "current_session_coverage_percent": coverage_percent,
            "actual_trading_value_count": len(values),
        },
        total_volume=total_volume,
        average_volume_5=_average(volume_windows[5]),
        average_volume_10=_average(volume_windows[10]),
        average_volume_20=_average(volume_windows[20]),
        relative_volume=(
            _pct(total_volume / mean(volume_windows[20][1:]))
            if len(volume_windows[20]) > 1 and mean(volume_windows[20][1:])
            else None
        ),
        total_actual_trading_value=sum(values) if values else None,
        average_actual_trading_value_5=_average(value_windows[5]),
        average_actual_trading_value_10=_average(value_windows[10]),
        average_actual_trading_value_20=_average(value_windows[20]),
        top5_volume_share_percent=share(top_volume, "volume", 5),
        top10_volume_share_percent=share(top_volume, "volume", 10),
        top5_trading_value_share_percent=share(top_value, "actual_trading_value", 5),
        top10_trading_value_share_percent=share(top_value, "actual_trading_value", 10),
        volume_expansion_count=volume_expansion,
        decline_heavy_volume_count=decline_heavy,
        leaders=leaders,
        limitations=limitations,
    )
    _persist_liquidity(response)
    return response

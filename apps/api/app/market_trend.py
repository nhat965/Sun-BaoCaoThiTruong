"""Deterministic market breadth and regime calculations.

The engine works only with canonical, persisted daily observations. It never
fills missing sessions, infers foreign flow, or turns a derived score into a
probability. Every response carries the denominator and data limitations used
to calculate it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import mean, pstdev

from sqlalchemy import select

from app.database import (
    MarketBreadthSnapshotRecord,
    MarketIndexObservationRecord,
    MarketRegimeSnapshotRecord,
    SecurityRecord,
    SessionLocal,
)
from app.freshness import assess_rows, utc
from app.price_integrity import canonical_daily_prices
from app.schemas import MarketBreadthPoint, MarketBreadthResponse, MarketRegimeResponse

BREADTH_FORMULA_VERSION = "market-breadth-v1"
REGIME_FORMULA_VERSION = "market-regime-v1"
INDEX_SYMBOLS = {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}


def _utc(value: datetime) -> datetime:
    return utc(value)


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 2)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _freshness(rows: object | list[object] | tuple[object, ...], now: datetime | None = None) -> str:
    """Return conservative freshness, retaining provenance/session evidence."""
    values = rows.values() if isinstance(rows, dict) else rows if isinstance(rows, (list, tuple)) else [rows]
    return assess_rows(values, now=now).status


def _history() -> tuple[list[SecurityRecord], dict[int, list[object]]]:
    with SessionLocal() as session:
        securities = list(
            session.scalars(
                select(SecurityRecord).where(
                    SecurityRecord.security_type == "stock",
                    SecurityRecord.listing_status == "active",
                )
            ).all()
        )
        ranked = canonical_daily_prices()
        rows = session.execute(
            select(ranked).where(ranked.c.session_rank <= 201)
        ).all()
    by_security: dict[int, list[object]] = defaultdict(list)
    for row in rows:
        by_security[row.security_id].append(row)
    for values in by_security.values():
        values.sort(key=lambda item: (item.market_session_date, item.market_timestamp), reverse=True)
    return securities, by_security


def _latest_session(
    securities: list[SecurityRecord], by_security: dict[int, list[object]]
) -> tuple[date | None, datetime | None, dict[int, object]]:
    latest = {
        security.id: by_security[security.id][0]
        for security in securities
        if by_security.get(security.id)
    }
    if not latest:
        return None, None, {}
    session_date = max(row.market_session_date for row in latest.values())
    current = {
        security_id: row
        for security_id, row in latest.items()
        if row.market_session_date == session_date
    }
    as_of = max((_utc(row.market_timestamp) for row in current.values()), default=None)
    return session_date, as_of, current


def _provenance(current: dict[int, object], now: datetime | None = None) -> tuple[str, str, str]:
    modes = {getattr(row, "source_mode", "unknown") for row in current.values()}
    validations = {getattr(row, "validation_status", "unvalidated") for row in current.values()}
    mode = next(iter(modes)) if len(modes) == 1 else "historical" if modes else "unavailable"
    validation = "valid" if validations == {"valid"} else "partial" if validations else "unvalidated"
    return mode, validation, _freshness(current, now)


def _ma_metrics(row_history: list[object], period: int) -> tuple[bool, bool] | None:
    if len(row_history) < period:
        return None
    closes = [float(row.close) for row in row_history[:period]]
    return float(row_history[0].close) > mean(closes), True


def _breadth_for_date(
    securities: list[SecurityRecord],
    by_security: dict[int, list[object]],
    target: date,
) -> MarketBreadthPoint | None:
    advancers = decliners = unchanged = traded = 0
    ma_counts = {20: [0, 0], 50: [0, 0], 200: [0, 0]}
    for security in securities:
        history = by_security.get(security.id, [])
        try:
            index = next(i for i, row in enumerate(history) if row.market_session_date == target)
        except StopIteration:
            continue
        row = history[index]
        traded += 1
        if index + 1 < len(history):
            previous = float(history[index + 1].close)
            close = float(row.close)
            if close > previous:
                advancers += 1
            elif close < previous:
                decliners += 1
            else:
                unchanged += 1
        for period, counts in ma_counts.items():
            window = history[index : index + period]
            if len(window) == period:
                counts[1] += 1
                if float(row.close) > mean(float(item.close) for item in window):
                    counts[0] += 1
    if traded == 0:
        return None
    return MarketBreadthPoint(
        market_session=target.isoformat(),
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        traded_securities=traded,
        above_ma20_percent=_pct(*ma_counts[20]),
        above_ma50_percent=_pct(*ma_counts[50]),
        above_ma200_percent=_pct(*ma_counts[200]),
    )


def _candidate_previous_session(session_date: date) -> date:
    candidate = session_date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _aligned_index_change_detail(
    rows: list[object], session_date: date, official_sessions: set[date] | None = None
) -> tuple[float | None, str]:
    """Return one-session change only when the previous session is evidenced.

    With an official calendar, the previous date must be the immediately prior
    official session.  Without one, a weekday candidate is accepted only when
    it matches the previous weekday (weekends are skipped); any weekday gap is
    returned as ``unconfirmed_gap`` instead of silently skipping a holiday.
    """
    by_session: dict[date, object] = {}
    conflicting_sessions: set[date] = set()
    for row in rows:
        row_date = getattr(row, "market_session_date", None)
        if row_date is not None and row_date <= session_date:
            existing = by_session.get(row_date)
            if existing is not None and float(existing.close) != float(row.close):
                conflicting_sessions.add(row_date)
            by_session.setdefault(row_date, row)
    ordered = [by_session[key] for key in sorted(by_session, reverse=True)]
    if len(ordered) < 2 or ordered[0].market_session_date != session_date:
        return None, "missing_target_session"
    if conflicting_sessions:
        return None, "duplicate_session_values"
    previous = ordered[1]
    if previous.close == 0:
        return None, "invalid_previous_close"
    previous_date = previous.market_session_date
    if official_sessions:
        eligible = sorted(item for item in official_sessions if item < session_date)
        if not eligible or previous_date != eligible[-1]:
            return None, "official_session_gap"
        alignment = "official_aligned"
    elif previous_date != _candidate_previous_session(session_date):
        return None, "unconfirmed_gap"
    else:
        alignment = "weekday_candidate_aligned"
    return round((float(ordered[0].close) / float(previous.close) - 1) * 100, 4), alignment


def _aligned_index_change(rows: list[object], session_date: date) -> float | None:
    """Compatibility wrapper returning only the verified change value."""
    change, _ = _aligned_index_change_detail(rows, session_date)
    return change


def _index_change(session_date: date) -> float | None:
    with SessionLocal() as session:
        rows = session.scalars(
            select(MarketIndexObservationRecord)
            .where(
                MarketIndexObservationRecord.symbol == "VNINDEX",
                MarketIndexObservationRecord.market_session_date <= session_date,
            )
            .order_by(
                MarketIndexObservationRecord.market_session_date.desc(),
                MarketIndexObservationRecord.market_timestamp.desc(),
            )
            .limit(20)
        ).all()
    return _aligned_index_change(rows, session_date)


def _index_change_detail(session_date: date) -> tuple[float | None, str]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(MarketIndexObservationRecord)
            .where(
                MarketIndexObservationRecord.symbol == "VNINDEX",
                MarketIndexObservationRecord.market_session_date <= session_date,
            )
            .order_by(
                MarketIndexObservationRecord.market_session_date.desc(),
                MarketIndexObservationRecord.market_timestamp.desc(),
            )
            .limit(20)
        ).all()
    return _aligned_index_change_detail(rows, session_date)


def _persist_breadth(response: MarketBreadthResponse) -> None:
    if response.market_session is None or response.as_of is None:
        return
    now = datetime.now(UTC)
    metrics = {
        "advancers": response.advancers,
        "decliners": response.decliners,
        "unchanged": response.unchanged,
        "traded_securities": response.traded_securities,
        "advance_decline_ratio": response.advance_decline_ratio,
        "advance_decline_difference": response.advance_decline_difference,
        "above_ma20": response.above_ma20,
        "above_ma20_denominator": response.above_ma20_denominator,
        "above_ma20_percent": response.above_ma20_percent,
        "above_ma50": response.above_ma50,
        "above_ma50_denominator": response.above_ma50_denominator,
        "above_ma50_percent": response.above_ma50_percent,
        "above_ma200": response.above_ma200,
        "above_ma200_denominator": response.above_ma200_denominator,
        "above_ma200_percent": response.above_ma200_percent,
        "new_highs_20": response.new_highs_20,
        "new_lows_20": response.new_lows_20,
    }
    with SessionLocal() as session:
        existing = session.scalar(
            select(MarketBreadthSnapshotRecord).where(
                MarketBreadthSnapshotRecord.market_session_date
                == date.fromisoformat(response.market_session),
                MarketBreadthSnapshotRecord.formula_version == response.formula_version,
            )
        )
        values = {
            "market_session_date": date.fromisoformat(response.market_session),
            "as_of": response.as_of,
            "provider": response.source or "canonical-price-selection",
            "data_mode": "historical",
            "validation_status": "valid" if response.data_status == "available" else "partial",
            "coverage_json": json.dumps(response.coverage, sort_keys=True),
            "metrics_json": json.dumps(metrics, sort_keys=True),
            "divergences_json": json.dumps(response.divergences, ensure_ascii=False),
            "warnings_json": json.dumps(response.warnings, ensure_ascii=False),
            "limitations_json": json.dumps(response.limitations, ensure_ascii=False),
            "formula_version": response.formula_version,
            "created_at": now,
        }
        if existing is None:
            session.add(MarketBreadthSnapshotRecord(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.commit()


def calculate_market_breadth(history_limit: int = 30, persist: bool = True) -> MarketBreadthResponse:
    securities, by_security = _history()
    universe_count = len(securities)
    session_date, as_of, current = _latest_session(securities, by_security)
    source = "canonical-price-selection"
    data_mode, validation_status, freshness = _provenance(current)
    if session_date is None or as_of is None:
        return MarketBreadthResponse(
            source=source,
            data_mode=data_mode,
            validation_status=validation_status,
            freshness=freshness,
            coverage={"universe_count": universe_count, "current_session_count": 0},
            warnings=["Chưa có quan sát giá hợp lệ để tính market breadth."],
            limitations=["Không suy diễn breadth từ dữ liệu thiếu hoặc từ chỉ số chưa có nguồn."],
        )

    point = _breadth_for_date(securities, by_security, session_date)
    if point is None:
        return MarketBreadthResponse(
            as_of=as_of,
            market_session=session_date.isoformat(),
            source=source,
            data_mode=data_mode,
            validation_status=validation_status,
            freshness=freshness,
            coverage={"universe_count": universe_count, "current_session_count": 0},
            warnings=["Không có mã đủ dữ liệu trong phiên được chọn."],
            limitations=["Không suy diễn breadth từ dữ liệu thiếu hoặc từ chỉ số chưa có nguồn."],
        )

    def counts(period: int) -> tuple[int, int]:
        eligible = [
            row for security_id in current if len(by_security.get(security_id, [])) >= period
            for row in [by_security[security_id]]
        ]
        above = sum(float(rows[0].close) > mean(float(item.close) for item in rows[:period]) for rows in eligible)
        return above, len(eligible)

    ma20, ma20_den = counts(20)
    ma50, ma50_den = counts(50)
    ma200, ma200_den = counts(200)
    changes = []
    new_highs = new_lows = 0
    for security_id, latest in current.items():
        history = by_security[security_id]
        if len(history) >= 2:
            changes.append(float(latest.close) - float(history[1].close))
        if len(history) >= 20:
            window = [float(item.close) for item in history[:20]]
            new_highs += float(latest.close) >= max(window)
            new_lows += float(latest.close) <= min(window)
    advancers = sum(value > 0 for value in changes)
    decliners = sum(value < 0 for value in changes)
    unchanged = sum(value == 0 for value in changes)
    historical_dates = sorted(
        {row.market_session_date for values in by_security.values() for row in values}, reverse=True
    )[:history_limit]
    historical = [
        historical_point
        for target in historical_dates
        if (historical_point := _breadth_for_date(securities, by_security, target)) is not None
    ]
    index_change, index_alignment = _index_change_detail(session_date)
    divergences: list[str] = []
    if index_change is None:
        index_limit = (
            "Chưa có VN-Index được cấp quyền; không kết luận phân kỳ với chỉ số."
            if index_alignment == "missing_target_session"
            else f"Không thể xác nhận phiên liền trước của VN-Index ({index_alignment}); không tính phân kỳ."
        )
    else:
        index_limit = None
        if index_change > 0 and decliners > advancers:
            divergences.append(
                "VN-Index tăng nhưng số mã giảm vượt số mã tăng; đây là phân kỳ cần theo dõi, không phải tín hiệu đảo chiều chắc chắn."
            )
        if index_change > 0 and ma20_den and _pct(ma20, ma20_den) is not None and _pct(ma20, ma20_den) < 50:
            divergences.append(
                "VN-Index tăng trong khi tỷ lệ mã trên MA20 dưới 50%; độ rộng ngắn hạn chưa xác nhận đồng thuận."
            )
    current_coverage = _pct(point.traded_securities, universe_count) or 0
    warnings = []
    if current_coverage < 80:
        warnings.append(f"Phiên {session_date.isoformat()} mới có {point.traded_securities}/{universe_count} mã đang hoạt động.")
    limitations = [
        "Mẫu số MA20/MA50/MA200 là số mã đủ số phiên tương ứng, không phải toàn bộ universe.",
        "Không có lịch nghỉ lễ chính thức nên không đánh dấu ngày thiếu dữ liệu là phiên giảm độ rộng.",
        "Không suy ra dòng tiền khối ngoại, tự doanh hoặc giá trị giao dịch thực tế từ OHLCV.",
    ]
    if index_limit:
        limitations.append(index_limit)
    response = MarketBreadthResponse(
        as_of=as_of,
        market_session=session_date.isoformat(),
        data_status="available" if current_coverage >= 80 else "partial",
        source=source,
        data_mode=data_mode,
        validation_status=validation_status,
        freshness=freshness,
        coverage={
            "universe_count": universe_count,
            "current_session_count": point.traded_securities,
            "current_session_coverage_percent": current_coverage,
            "two_session_count": len(changes),
            "ma20_eligible_count": ma20_den,
            "ma50_eligible_count": ma50_den,
            "ma200_eligible_count": ma200_den,
            "index_session_alignment_verified": int(index_change is not None),
        },
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        traded_securities=point.traded_securities,
        advance_decline_ratio=_safe_ratio(advancers, decliners),
        advance_decline_difference=advancers - decliners,
        above_ma20=ma20,
        above_ma20_denominator=ma20_den,
        above_ma20_percent=_pct(ma20, ma20_den),
        above_ma50=ma50,
        above_ma50_denominator=ma50_den,
        above_ma50_percent=_pct(ma50, ma50_den),
        above_ma200=ma200,
        above_ma200_denominator=ma200_den,
        above_ma200_percent=_pct(ma200, ma200_den),
        new_highs_20=new_highs,
        new_lows_20=new_lows,
        divergences=divergences,
        historical=historical,
        warnings=warnings,
        limitations=limitations,
    )
    if persist:
        _persist_breadth(response)
    return response


def _persist_regime(response: MarketRegimeResponse) -> None:
    if response.market_session is None or response.as_of is None:
        return
    now = datetime.now(UTC)
    with SessionLocal() as session:
        existing = session.scalar(
            select(MarketRegimeSnapshotRecord).where(
                MarketRegimeSnapshotRecord.market_session_date
                == date.fromisoformat(response.market_session),
                MarketRegimeSnapshotRecord.formula_version == response.formula_version,
            )
        )
        values = {
            "market_session_date": date.fromisoformat(response.market_session),
            "as_of": response.as_of,
            "regime": response.regime,
            "provider": response.source or "canonical-price-selection",
            "data_mode": "historical",
            "validation_status": "valid" if response.data_status == "available" else "partial",
            "coverage_json": json.dumps(response.coverage, sort_keys=True),
            "indicators_json": json.dumps(response.indicators, sort_keys=True),
            "evidence_json": json.dumps(response.evidence, ensure_ascii=False),
            "conflicts_json": json.dumps(response.conflicting_signals, ensure_ascii=False),
            "warnings_json": json.dumps(response.warnings, ensure_ascii=False),
            "limitations_json": json.dumps(response.limitations, ensure_ascii=False),
            "formula_version": response.formula_version,
            "created_at": now,
        }
        if existing is None:
            session.add(MarketRegimeSnapshotRecord(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.commit()


def calculate_market_regime(persist: bool = True) -> MarketRegimeResponse:
    breadth = calculate_market_breadth(persist=persist)
    if breadth.as_of is None or breadth.market_session is None:
        return MarketRegimeResponse(
            source=breadth.source,
            data_mode=breadth.data_mode,
            validation_status=breadth.validation_status,
            freshness=breadth.freshness,
            coverage=breadth.coverage,
            warnings=["Chưa đủ dữ liệu để phân loại regime."],
            limitations=breadth.limitations,
        )
    securities, by_security = _history()
    session_date = date.fromisoformat(breadth.market_session)
    _, _, current = _latest_session(securities, by_security)
    volatilities = []
    for security_id in current:
        history = by_security.get(security_id, [])
        if len(history) < 20:
            continue
        returns = [
            float(history[i].close) / float(history[i + 1].close) - 1
            for i in range(19)
            if float(history[i + 1].close) != 0
        ]
        if len(returns) >= 10:
            volatilities.append(pstdev(returns) * (252**0.5) * 100)
    volatility = round(mean(volatilities), 4) if volatilities else None
    ma20 = breadth.above_ma20_percent
    ma50 = breadth.above_ma50_percent
    ma200 = breadth.above_ma200_percent
    coverage_percent = float(breadth.coverage.get("current_session_coverage_percent", 0))
    ma200_den = int(breadth.above_ma200_denominator or 0)
    if coverage_percent < 50 or ma50 is None or ma200 is None or ma200_den < 5:
        regime = "UNCERTAIN"
    elif volatility is not None and volatility >= 45:
        regime = "VOLATILE"
    elif ma20 is not None and ma50 is not None and ma200 is not None and ma20 >= 60 and ma50 >= 55 and ma200 >= 50:
        regime = "UPTREND"
    elif ma20 is not None and ma50 is not None and ma200 is not None and ma20 <= 40 and ma50 <= 45 and ma200 <= 50:
        regime = "DOWNTREND"
    else:
        regime = "SIDEWAYS"
    evidence = [
        f"{breadth.above_ma20 or 0}/{breadth.above_ma20_denominator or 0} mã đủ điều kiện đang trên MA20 ({ma20 if ma20 is not None else 'chưa có'}%).",
        f"{breadth.above_ma50 or 0}/{breadth.above_ma50_denominator or 0} mã đủ điều kiện đang trên MA50 ({ma50 if ma50 is not None else 'chưa có'}%).",
        f"{breadth.above_ma200 or 0}/{breadth.above_ma200_denominator or 0} mã đủ điều kiện đang trên MA200 ({ma200 if ma200 is not None else 'chưa có'}%).",
    ]
    if volatility is not None:
        evidence.append(f"Độ biến động thực hiện trung bình 20 phiên của mã đủ dữ liệu: {volatility:.2f}%/năm hóa.")
    conflicts: list[str] = []
    available_ma = [value for value in (ma20, ma50, ma200) if value is not None]
    if available_ma and max(available_ma) - min(available_ma) >= 30:
        conflicts.append("Các lớp MA cho tín hiệu không đồng thuận; cần theo dõi thay vì kết luận một chiều.")
    if breadth.advance_decline_difference is not None and ma20 is not None:
        if breadth.advance_decline_difference > 0 and ma20 < 50:
            conflicts.append("A/D dương nhưng MA20 breadth dưới 50%.")
        if breadth.advance_decline_difference < 0 and ma20 >= 50:
            conflicts.append("A/D âm nhưng MA20 breadth từ 50% trở lên.")
    warnings = list(breadth.warnings)
    if regime == "UNCERTAIN":
        warnings.append("Độ phủ hoặc độ dài lịch sử chưa đủ để phân loại regime đáng tin cậy.")
    limitations = list(breadth.limitations)
    limitations.append("Regime là phân loại quy tắc, không phải xác suất tăng/giảm và chưa được hiệu chỉnh backtest.")
    response = MarketRegimeResponse(
        as_of=breadth.as_of,
        market_session=session_date.isoformat(),
        data_status=breadth.data_status,
        source=breadth.source,
        data_mode=breadth.data_mode,
        validation_status=breadth.validation_status,
        freshness=breadth.freshness,
        regime=regime,
        indicators={
            "above_ma20_percent": ma20,
            "above_ma50_percent": ma50,
            "above_ma200_percent": ma200,
            "advance_decline_difference": breadth.advance_decline_difference,
            "realized_volatility_20d_annualized_percent": volatility,
            "current_session_coverage_percent": coverage_percent,
        },
        evidence=evidence,
        conflicting_signals=conflicts,
        coverage=breadth.coverage,
        warnings=warnings,
        limitations=limitations,
    )
    if persist:
        _persist_regime(response)
    return response

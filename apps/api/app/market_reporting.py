"""Deterministic market breadth and daily report snapshots from persisted observations."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import desc, func, select

from app.database import PriceObservation, ReportSnapshotRecord, SecurityRecord, SessionLocal
from app.schemas import DailyMarketReport, MarketIndexObservation, MarketOverview


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_market_overview() -> MarketOverview:
    with SessionLocal() as session:
        securities = list(
            session.scalars(
                select(SecurityRecord).where(SecurityRecord.listing_status == "active")
            ).all()
        )
        ranked = (
            select(
                PriceObservation.security_id.label("security_id"),
                PriceObservation.close.label("close"),
                PriceObservation.volume.label("volume"),
                PriceObservation.market_timestamp.label("market_timestamp"),
                PriceObservation.provider.label("provider"),
                PriceObservation.source_mode.label("source_mode"),
                func.row_number()
                .over(
                    partition_by=PriceObservation.security_id,
                    order_by=desc(PriceObservation.market_timestamp),
                )
                .label("position"),
            )
            .subquery()
        )
        rows = session.execute(select(ranked).where(ranked.c.position <= 2)).all()

    observations = defaultdict(list)
    for row in rows:
        observations[row.security_id].append(row)
    for values in observations.values():
        values.sort(key=lambda item: item.market_timestamp, reverse=True)

    stocks = [item for item in securities if item.security_type == "stock"]
    eligible = [item for item in stocks if len(observations[item.id]) >= 2]
    coverage = round(len(eligible) / len(stocks) * 100, 2) if stocks else 0
    if not eligible:
        return MarketOverview(
            status="unavailable",
            active_stock_count=len(stocks),
            limitations=[
                "Cần ít nhất hai phiên giá đã lưu cho một mã để tính market breadth.",
                "Không có dữ liệu chỉ số hoặc foreign trading được suy đoán.",
            ],
        )

    as_of = max(_utc(observations[item.id][0].market_timestamp) for item in eligible)
    fresh_cutoff = as_of - timedelta(days=4)
    fresh = [
        item
        for item in eligible
        if _utc(observations[item.id][0].market_timestamp) >= fresh_cutoff
    ]
    changes = {}
    total_volume = 0
    estimated_value = 0.0
    source_modes = set()
    sources = set()
    for security in fresh:
        latest, previous = observations[security.id][:2]
        change = (float(latest.close) / float(previous.close) - 1) * 100
        changes[security.id] = change
        total_volume += latest.volume
        estimated_value += float(latest.close) * latest.volume
        source_modes.add(latest.source_mode)
        sources.add(latest.provider)

    advancers = sum(change > 0 for change in changes.values())
    decliners = sum(change < 0 for change in changes.values())
    unchanged = sum(change == 0 for change in changes.values())
    sectors = defaultdict(list)
    for security in fresh:
        if security.sector and security.id in changes:
            sectors[security.sector].append(changes[security.id])
    sector_performance = {
        sector: round(sum(values) / len(values), 4)
        for sector, values in sorted(sectors.items())
    }
    indices = []
    for security in securities:
        if security.security_type != "index" or not observations[security.id]:
            continue
        latest = observations[security.id][0]
        previous = observations[security.id][1] if len(observations[security.id]) > 1 else None
        indices.append(
            MarketIndexObservation(
                symbol=security.symbol,
                name=security.name,
                close=float(latest.close),
                change_percent=(
                    round((float(latest.close) / float(previous.close) - 1) * 100, 4)
                    if previous
                    else None
                ),
                market_timestamp=_utc(latest.market_timestamp),
                source=latest.provider,
            )
        )
    normalized_modes = {mode for mode in source_modes if mode in {"live", "fixture"}}
    source_mode = (
        next(iter(normalized_modes))
        if len(normalized_modes) == 1
        else ("mixed" if len(normalized_modes) > 1 else "unknown")
    )
    limitations = [
        "Giá trị giao dịch là close × volume từ quan sát lưu trữ, không thay thế số liệu chính thức.",
        "Chưa có dữ liệu mua bán ròng nước ngoài đã xác minh.",
    ]
    if not indices:
        limitations.append("Chưa có chuỗi VN-Index/VN30/HNX-Index/UPCoM được lưu.")
    if coverage < 80:
        limitations.append(f"Breadth mới phủ {coverage:.2f}% mã đang hoạt động.")
    return MarketOverview(
        status="available" if coverage >= 80 and source_mode == "live" else "partial",
        as_of=as_of,
        source_mode=source_mode,
        sources=sorted(sources),
        active_stock_count=len(stocks),
        stocks_with_two_sessions=len(fresh),
        coverage_percent=coverage,
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        total_volume=total_volume,
        estimated_trading_value=round(estimated_value, 4),
        indices=indices,
        sector_performance_percent=sector_performance,
        limitations=limitations,
    )


def create_daily_market_report(report_type: str, trading_date: date | None = None) -> DailyMarketReport:
    if report_type not in {"pre_market", "post_market"}:
        raise ValueError("report_type must be pre_market or post_market")
    overview = build_market_overview()
    selected_date = trading_date or (overview.as_of.date() if overview.as_of else datetime.now(UTC).date())
    if selected_date.weekday() >= 5:
        raise ValueError("Daily market reports are not generated for weekends")
    date_stamp = datetime.combine(selected_date, time.min, tzinfo=UTC)
    sections = {
        "market": [
            (
                f"Breadth: {overview.advancers} tăng, {overview.decliners} giảm, "
                f"{overview.unchanged} đứng giá."
                if overview.advancers is not None
                else "Market breadth chưa khả dụng."
            ),
            (
                f"Khối lượng từ dữ liệu lưu trữ: {overview.total_volume:,}."
                if overview.total_volume is not None
                else "Thanh khoản chưa khả dụng."
            ),
        ],
        "watchlist": ["Watchlist cần được cấu hình bởi người dùng; báo cáo không tự chọn mã."],
        "risks": list(overview.limitations),
    }
    if report_type == "pre_market":
        sections["scenarios"] = [
            "Dùng dữ liệu phiên trước làm mốc; không suy đoán sự kiện qua đêm khi chưa có nguồn."
        ]
    else:
        sections["sectors"] = [
            f"{sector}: {change:+.2f}%"
            for sector, change in overview.sector_performance_percent.items()
        ] or ["Chưa đủ dữ liệu phân ngành để tính hiệu suất."]
    snapshot = DailyMarketReport(
        snapshot_key=f"market-{report_type}:{selected_date.isoformat()}",
        report_type=report_type,
        trading_date=date_stamp,
        source_mode=overview.source_mode,
        sections=sections,
        created_at=datetime.now(UTC),
    )
    with SessionLocal() as session:
        existing = session.scalar(
            select(ReportSnapshotRecord).where(
                ReportSnapshotRecord.snapshot_key == snapshot.snapshot_key
            )
        )
        values = {
            "report_type": report_type,
            "symbol": None,
            "trading_date": date_stamp,
            "source_mode": overview.source_mode,
            "payload_json": snapshot.model_dump_json(),
            "created_at": snapshot.created_at,
        }
        if existing is None:
            session.add(ReportSnapshotRecord(snapshot_key=snapshot.snapshot_key, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.commit()
    return snapshot


def list_report_snapshots(limit: int = 50) -> list[DailyMarketReport]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(ReportSnapshotRecord)
            .where(ReportSnapshotRecord.report_type.in_(["pre_market", "post_market", "stock_eod"]))
            .order_by(ReportSnapshotRecord.created_at.desc())
            .limit(limit)
        ).all()
        return [DailyMarketReport.model_validate_json(row.payload_json) for row in rows]

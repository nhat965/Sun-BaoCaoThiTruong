"""Market data foundation: session semantics, universe coverage and index storage.

This module intentionally does not manufacture index, holiday, market-cap or foreign-flow
values. It exposes explicit gaps until an authorized provider supplies those records.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.database import MarketIndexObservationRecord, SecurityRecord, SessionLocal
from app.price_integrity import canonical_daily_prices, provider_id_for
from app.schemas import MarketIndexObservation, MarketIndicesResponse

ALLOWED_EXCHANGES = {"HOSE", "HNX", "UPCOM"}
ALLOWED_INDEX_MODES = {"live", "delayed", "historical", "stale", "fixture", "unavailable"}
ALLOWED_VALIDATION = {"valid", "partial", "unvalidated", "invalid"}


class CalendarStatus(BaseModel):
    exchange: str
    session_date: date
    status: str
    source: str
    limitations: list[str] = Field(default_factory=list)


class VietnamMarketCalendar:
    """Conservative Vietnam session calendar.

    Weekends are deterministically non-trading. Weekdays are only a
    ``trading_candidate`` because the project has no licensed official holiday calendar yet.
    This prevents a holiday from being misclassified as a missing candle.
    """

    def __init__(self, timezone_name: str | None = None) -> None:
        self.timezone = ZoneInfo(timezone_name or get_settings().market_timezone)

    def session_date(self, timestamp: datetime) -> date:
        if timestamp.tzinfo is None:
            raise ValueError("Market timestamp must include a timezone")
        return timestamp.astimezone(self.timezone).date()

    def classify(self, session_date: date, exchange: str) -> CalendarStatus:
        exchange = exchange.strip().upper()
        if exchange not in ALLOWED_EXCHANGES:
            raise ValueError(f"Unsupported Vietnam exchange: {exchange}")
        if session_date.weekday() >= 5:
            return CalendarStatus(
                exchange=exchange,
                session_date=session_date,
                status="weekend",
                source="deterministic_weekend_rule",
            )
        return CalendarStatus(
            exchange=exchange,
            session_date=session_date,
            status="trading_candidate",
            source="weekday_rule",
            limitations=[
                "Official HOSE/HNX/UPCoM holiday calendar is not connected; weekday status is not confirmation of a completed session."
            ],
        )


class MarketUniverseCoverage(BaseModel):
    universe_count: int = 0
    active_count: int = 0
    exchange_distribution: dict[str, int] = Field(default_factory=dict)
    history_20_count: int = 0
    history_50_count: int = 0
    history_200_count: int = 0
    market_cap_count: int = 0
    foreign_flow_count: int = 0


def canonical_market_universe() -> MarketUniverseCoverage:
    with SessionLocal() as session:
        universe = list(
            session.scalars(
                select(SecurityRecord).where(SecurityRecord.security_type == "stock")
            ).all()
        )
        active = [row for row in universe if row.listing_status == "active"]
        exchange_distribution = {
            exchange: count
            for exchange, count in session.execute(
                select(SecurityRecord.exchange, func.count(SecurityRecord.id))
                .where(
                    SecurityRecord.security_type == "stock",
                    SecurityRecord.listing_status == "active",
                )
                .group_by(SecurityRecord.exchange)
            )
        }
        ranked = canonical_daily_prices()
        rows = session.execute(
            select(ranked.c.security_id, ranked.c.market_session_date).where(
                ranked.c.session_rank <= 200
            )
        ).all()

    sessions: dict[int, set[date]] = defaultdict(set)
    for security_id, session_date in rows:
        sessions[security_id].add(session_date)
    counts = [len(sessions.get(row.id, set())) for row in active]
    return MarketUniverseCoverage(
        universe_count=len(universe),
        active_count=len(active),
        exchange_distribution=exchange_distribution,
        history_20_count=sum(count >= 20 for count in counts),
        history_50_count=sum(count >= 50 for count in counts),
        history_200_count=sum(count >= 200 for count in counts),
        market_cap_count=0,
        foreign_flow_count=0,
    )


class MarketIndexImportResult(BaseModel):
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0
    errors: list[str] = Field(default_factory=list)


def _datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _decimal(value: str | None, field: str, *, required: bool = False) -> Decimal | None:
    if value is None or not value.strip():
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        result = Decimal(value.strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result <= 0 and field in {"close", "previous_close"}:
        raise ValueError(f"{field} must be positive")
    return result


def import_market_indices(csv_content: str, source_name: str) -> MarketIndexImportResult:
    required = {
        "symbol",
        "name",
        "exchange",
        "market_session_date",
        "market_timestamp",
        "close",
        "provider",
        "retrieved_at",
        "data_mode",
        "validation_status",
    }
    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        missing = sorted(required - set(reader.fieldnames or []))
        raise ValueError(f"Invalid index CSV schema; missing: {', '.join(missing)}")

    result = MarketIndexImportResult()
    with SessionLocal() as session:
        for row_number, row in enumerate(reader, start=2):
            try:
                symbol = (row.get("symbol") or "").strip().upper()
                name = (row.get("name") or "").strip()
                exchange = (row.get("exchange") or "").strip().upper()
                provider = (row.get("provider") or source_name).strip()
                provider_id = provider_id_for(provider)
                if not symbol or not name or not provider:
                    raise ValueError("symbol, name and provider are required")
                if exchange not in ALLOWED_EXCHANGES:
                    raise ValueError(f"exchange must be one of {sorted(ALLOWED_EXCHANGES)}")
                session_date = _date(row["market_session_date"], "market_session_date")
                market_timestamp = _datetime(row["market_timestamp"], "market_timestamp")
                retrieved_at = _datetime(row["retrieved_at"], "retrieved_at")
                close = _decimal(row.get("close"), "close", required=True)
                previous_close = _decimal(row.get("previous_close"), "previous_close")
                data_mode = (row.get("data_mode") or "").strip().lower()
                validation_status = (row.get("validation_status") or "").strip().lower()
                if data_mode not in ALLOWED_INDEX_MODES:
                    raise ValueError(f"unsupported data_mode: {data_mode}")
                if validation_status not in ALLOWED_VALIDATION:
                    raise ValueError(f"unsupported validation_status: {validation_status}")
                last_updated = _datetime(row.get("last_updated") or row["retrieved_at"], "last_updated")
                values = {
                    "symbol": symbol,
                    "name": name,
                    "exchange": exchange,
                    "market_session_date": session_date,
                    "market_timestamp": market_timestamp,
                    "close": close,
                    "previous_close": previous_close,
                    "provider": provider,
                    "provider_id": provider_id,
                    "source_url": (row.get("source_url") or "").strip() or None,
                    "retrieved_at": retrieved_at,
                    "last_updated": last_updated,
                    "data_mode": data_mode,
                    "validation_status": validation_status,
                    "coverage": (row.get("coverage") or "index").strip() or "index",
                    "freshness": (row.get("freshness") or "unknown").strip() or "unknown",
                    "adjustment_policy": (
                        row.get("adjustment_policy") or "unknown"
                    ).strip()
                    or "unknown",
                }
                existing = session.scalar(
                    select(MarketIndexObservationRecord).where(
                        MarketIndexObservationRecord.symbol == symbol,
                        MarketIndexObservationRecord.provider_id == provider_id,
                        MarketIndexObservationRecord.market_session_date == session_date,
                    )
                )
                material_keys = {
                    key for key in values if key != "last_updated"
                }
                if existing is None:
                    session.add(MarketIndexObservationRecord(**values))
                    result.inserted += 1
                elif all(getattr(existing, key) == values[key] for key in material_keys) or (
                    existing.validation_status == "valid"
                    and validation_status != "valid"
                ):
                    result.skipped += 1
                else:
                    for key, value in values.items():
                        setattr(existing, key, value)
                    result.updated += 1
            except (KeyError, ValueError) as exc:
                result.rejected += 1
                result.errors.append(f"row {row_number}: {exc}")
        session.commit()
    return result


def _index_schema(row: MarketIndexObservationRecord) -> MarketIndexObservation:
    change = None
    if row.previous_close is not None and row.previous_close != 0:
        change = round((float(row.close) / float(row.previous_close) - 1) * 100, 6)
    return MarketIndexObservation(
        symbol=row.symbol,
        name=row.name,
        close=float(row.close),
        change_percent=change,
        market_timestamp=row.market_timestamp,
        source=row.provider,
        provider=row.provider,
        source_url=row.source_url,
        market_session=row.market_session_date.isoformat(),
        retrieved_at=row.retrieved_at,
        last_updated=row.last_updated,
        data_mode=row.data_mode,
        validation_status=row.validation_status,
        coverage=row.coverage,
        freshness=row.freshness,
        adjustment_policy=row.adjustment_policy,
    )


def list_market_indices() -> MarketIndicesResponse:
    with SessionLocal() as session:
        rows = session.scalars(
            select(MarketIndexObservationRecord).order_by(
                MarketIndexObservationRecord.market_session_date.desc(),
                MarketIndexObservationRecord.market_timestamp.desc(),
                MarketIndexObservationRecord.id.desc(),
            )
        ).all()

    latest: dict[str, MarketIndexObservationRecord] = {}
    for row in rows:
        latest.setdefault(row.symbol, row)
    selected = list(latest.values())
    if not selected:
        return MarketIndicesResponse(
            data_status="unavailable",
            coverage={"available_count": 0, "expected_count": 4, "coverage_percent": 0},
            warnings=["Chưa có quan sát chỉ số được cấp quyền lưu trữ."],
            limitations=[
                "VN-Index, VN30, HNX-Index và UPCoM-Index chưa được tự suy diễn từ dữ liệu cổ phiếu."
            ],
        )
    latest_timestamp = max(row.market_timestamp for row in selected)
    status = "available"
    if any(row.validation_status != "valid" or row.data_mode in {"stale", "unavailable"} for row in selected):
        status = "partial"
    return MarketIndicesResponse(
        as_of=latest_timestamp,
        market_session=max(row.market_session_date for row in selected).isoformat(),
        data_status=status,
        source=", ".join(sorted({row.provider for row in selected})),
        coverage={
            "available_count": len(selected),
            "expected_count": 4,
            "coverage_percent": round(min(len(selected), 4) / 4 * 100, 2),
        },
        indices=[_index_schema(row) for row in sorted(selected, key=lambda item: item.symbol)],
        warnings=[],
        limitations=[
            "Độ phủ chỉ số phản ánh số mã đã được nguồn cung cấp; không tự suy ra chỉ số còn thiếu."
        ],
    )

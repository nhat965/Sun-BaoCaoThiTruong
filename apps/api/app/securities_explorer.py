from datetime import UTC, datetime
from math import ceil
from typing import Literal

from sqlalchemy import and_, case, func, or_, select

from app.database import (
    FinancialMetricRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
)
from app.schemas import SecuritiesExplorerItem, SecuritiesExplorerResponse
from app.text import normalize_vietnamese

SecuritiesSort = Literal["symbol", "name", "price", "change", "volume"]
SortOrder = Literal["asc", "desc"]


def _latest_metric(metric_name: str):
    return (
        select(FinancialMetricRecord.value)
        .where(
            FinancialMetricRecord.security_id == SecurityRecord.id,
            FinancialMetricRecord.metric_name == metric_name,
        )
        .order_by(
            FinancialMetricRecord.calculated_at.desc(),
            FinancialMetricRecord.id.desc(),
        )
        .limit(1)
        .correlate(SecurityRecord)
        .scalar_subquery()
    )


def list_securities(
    *,
    page: int,
    page_size: int,
    query: str | None = None,
    exchange: str | None = None,
    sector: str | None = None,
    listing_status: str | None = None,
    sort_by: SecuritiesSort = "symbol",
    sort_order: SortOrder = "asc",
) -> SecuritiesExplorerResponse:
    ranked_prices = (
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
                order_by=(
                    PriceObservation.market_timestamp.desc(),
                    PriceObservation.id.desc(),
                ),
            )
            .label("price_rank"),
        )
        .where(PriceObservation.validation_status != "invalid")
        .subquery()
    )
    latest = (
        select(ranked_prices)
        .where(ranked_prices.c.price_rank == 1)
        .subquery("latest_price")
    )
    previous = (
        select(
            ranked_prices.c.security_id,
            ranked_prices.c.close.label("previous_close"),
        )
        .where(ranked_prices.c.price_rank == 2)
        .subquery("previous_price")
    )
    change_percent = case(
        (
            and_(previous.c.previous_close.is_not(None), previous.c.previous_close != 0),
            (latest.c.close - previous.c.previous_close) * 100 / previous.c.previous_close,
        ),
        else_=None,
    ).label("change_percent")
    trading_value = (latest.c.close * latest.c.volume).label("trading_value")
    pe = _latest_metric("pe").label("pe")
    pb = _latest_metric("pb").label("pb")

    conditions = []
    normalized_query = normalize_vietnamese(query or "")
    if normalized_query:
        pattern = f"%{normalized_query}%"
        conditions.append(
            or_(
                func.lower(SecurityRecord.symbol).like(pattern),
                SecurityRecord.normalized_name.like(pattern),
                func.lower(SecurityRecord.aliases_json).like(pattern),
            )
        )
    if exchange:
        conditions.append(SecurityRecord.exchange == exchange.upper())
    if sector:
        conditions.append(SecurityRecord.sector == sector)
    if listing_status:
        conditions.append(SecurityRecord.listing_status == listing_status)

    sort_columns = {
        "symbol": SecurityRecord.symbol,
        "name": SecurityRecord.normalized_name,
        "price": latest.c.close,
        "change": change_percent,
        "volume": latest.c.volume,
    }
    sort_column = sort_columns[sort_by]
    ordered = sort_column.desc().nulls_last() if sort_order == "desc" else sort_column.asc().nulls_last()

    statement = (
        select(
            SecurityRecord,
            latest.c.close,
            latest.c.volume,
            latest.c.market_timestamp,
            latest.c.provider,
            latest.c.source_mode,
            change_percent,
            trading_value,
            pe,
            pb,
        )
        .outerjoin(latest, latest.c.security_id == SecurityRecord.id)
        .outerjoin(previous, previous.c.security_id == SecurityRecord.id)
        .where(*conditions)
        .order_by(ordered, SecurityRecord.symbol.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    with SessionLocal() as session:
        total = int(
            session.scalar(
                select(func.count(SecurityRecord.id)).where(*conditions)
            )
            or 0
        )
        rows = session.execute(statement).all()
        exchanges = list(
            session.scalars(
                select(SecurityRecord.exchange).distinct().order_by(SecurityRecord.exchange)
            )
        )
        sectors = list(
            session.scalars(
                select(SecurityRecord.sector)
                .where(SecurityRecord.sector.is_not(None))
                .distinct()
                .order_by(SecurityRecord.sector)
            )
        )
        statuses = list(
            session.scalars(
                select(SecurityRecord.listing_status)
                .distinct()
                .order_by(SecurityRecord.listing_status)
            )
        )

    items = [
        SecuritiesExplorerItem(
            symbol=row.SecurityRecord.symbol,
            name=row.SecurityRecord.name,
            exchange=row.SecurityRecord.exchange,
            industry=row.SecurityRecord.industry,
            sector=row.SecurityRecord.sector,
            listing_status=row.SecurityRecord.listing_status,
            currency=row.SecurityRecord.currency,
            latest_price=float(row.close) if row.close is not None else None,
            change_percent=float(row.change_percent) if row.change_percent is not None else None,
            volume=int(row.volume) if row.volume is not None else None,
            trading_value=float(row.trading_value) if row.trading_value is not None else None,
            pe=float(row.pe) if row.pe is not None else None,
            pb=float(row.pb) if row.pb is not None else None,
            price_updated_at=row.market_timestamp,
            price_source=row.provider,
            price_source_mode=row.source_mode,
            registry_updated_at=row.SecurityRecord.last_updated,
        )
        for row in rows
    ]
    return SecuritiesExplorerResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
        available_exchanges=exchanges,
        available_sectors=sectors,
        available_listing_statuses=statuses,
        generated_at=datetime.now(UTC),
    )

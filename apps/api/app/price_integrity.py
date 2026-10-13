"""Canonical daily price selection and Vietnam market-session normalization."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select

from app.config import Settings, get_settings
from app.database import PriceObservation

SOURCE_PROVIDER_IDS = {
    "Yahoo Finance chart": "yahoo",
    "Synthetic fixture (development only)": "fixture",
}


def provider_id_for(source: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip().lower()
    return SOURCE_PROVIDER_IDS.get(source, source.strip().lower().replace(" ", "_"))


def market_session_date(timestamp: datetime, timezone_name: str) -> date:
    if timestamp.tzinfo is None:
        raise ValueError("Market timestamp must include a timezone")
    return timestamp.astimezone(ZoneInfo(timezone_name)).date()


def canonical_daily_prices(settings: Settings | None = None):
    """Return one trusted observation per security/session, then rank distinct sessions."""
    settings = settings or get_settings()
    configured = [
        item.strip().lower()
        for item in settings.market_provider_priority.split(",")
        if item.strip()
    ]
    priority = {provider_id: rank for rank, provider_id in enumerate(configured)}
    # Development-only Yahoo and fixtures remain explicitly lower-trust fallbacks.
    priority.setdefault("yahoo", 100)
    priority.setdefault("fixture", 10_000)
    provider_rank = case(priority, value=PriceObservation.provider_id, else_=1_000)
    validation_rank = case(
        (PriceObservation.validation_status == "valid", 0),
        (PriceObservation.validation_status == "partial", 1),
        else_=2,
    )
    candidate = (
        select(
            PriceObservation.id.label("id"),
            PriceObservation.security_id.label("security_id"),
            PriceObservation.close.label("close"),
            PriceObservation.volume.label("volume"),
            PriceObservation.actual_trading_value.label("actual_trading_value"),
            PriceObservation.market_cap.label("market_cap"),
            PriceObservation.market_timestamp.label("market_timestamp"),
            PriceObservation.market_session_date.label("market_session_date"),
            PriceObservation.ingested_at.label("retrieved_at"),
            PriceObservation.provider.label("provider"),
            PriceObservation.provider_id.label("provider_id"),
            PriceObservation.source_mode.label("source_mode"),
            PriceObservation.validation_status.label("validation_status"),
            PriceObservation.freshness.label("freshness"),
            validation_rank.label("validation_rank"),
            PriceObservation.adjusted.label("adjusted"),
            provider_rank.label("provider_rank"),
            case((PriceObservation.source_mode == "fixture", 1), else_=0).label(
                "fixture_rank"
            ),
        )
        .where(
            PriceObservation.interval == "1d",
            PriceObservation.validation_status != "invalid",
        )
        .subquery("eligible_daily_prices")
    )
    per_session = (
        select(
            candidate,
            func.row_number()
            .over(
                partition_by=(
                    candidate.c.security_id,
                    candidate.c.market_session_date,
                ),
                order_by=(
                    candidate.c.fixture_rank.asc(),
                    candidate.c.provider_rank.asc(),
                    candidate.c.validation_rank.asc(),
                    candidate.c.adjusted.asc(),
                    candidate.c.retrieved_at.desc(),
                    candidate.c.id.desc(),
                ),
            )
            .label("candidate_rank"),
        )
        .subquery("daily_price_candidates")
    )
    canonical = (
        select(per_session).where(per_session.c.candidate_rank == 1).subquery("canonical_daily")
    )
    return (
        select(
            canonical,
            func.row_number()
            .over(
                partition_by=canonical.c.security_id,
                order_by=(
                    canonical.c.market_session_date.desc(),
                    canonical.c.market_timestamp.desc(),
                    canonical.c.id.desc(),
                ),
            )
            .label("session_rank"),
        )
        .subquery("ranked_canonical_daily")
    )

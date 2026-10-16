"""Database-backed data coverage. Values are counts of persisted observations only."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import Settings
from app.data_pipeline import provider_catalog
from app.database import (
    FinancialPeriodRecord,
    MarketIndexObservationRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
    SourceHealthRecord,
)

EXPECTED_INDICES = ("VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX")


def build_data_coverage(settings: Settings) -> dict:
    generated_at = datetime.now(UTC)
    with SessionLocal() as session:
        securities = list(session.scalars(select(SecurityRecord)).all())
        prices = list(session.scalars(select(PriceObservation)).all())
        indices = list(session.scalars(select(MarketIndexObservationRecord)).all())
        financials = list(session.scalars(select(FinancialPeriodRecord)).all())
        health = list(session.scalars(select(SourceHealthRecord)).all())

    stocks = [row for row in securities if row.security_type == "stock"]
    active = [row for row in stocks if row.listing_status == "active"]
    per_security: dict[int, list[PriceObservation]] = {}
    for row in prices:
        per_security.setdefault(row.security_id, []).append(row)
    for rows in per_security.values():
        rows.sort(key=lambda item: item.market_session_date, reverse=True)
    latest_sessions = [rows[0].market_session_date for rows in per_security.values() if rows]
    latest_session = max(latest_sessions).isoformat() if latest_sessions else None
    latest_retrieved_row = max(prices, key=lambda row: row.ingested_at) if prices else None
    stale_cutoff = generated_at.date() - timedelta(days=4)
    latest_price_ids = {security_id for security_id, rows in per_security.items() if rows and rows[0].market_session_date >= stale_cutoff}
    price_validation_errors = sum(1 for row in prices if row.validation_status not in {"valid", "partial"})
    actual_value = sum(1 for row in prices if row.actual_trading_value is not None)
    market_cap = sum(1 for row in prices if row.market_cap is not None)
    foreign_flow = 0  # no foreign-flow column/table is treated as unavailable, never zero-valued.

    exchange_counts = {}
    for exchange in {row.exchange for row in securities}:
        exchange_counts[exchange] = {
            "total": sum(row.exchange == exchange for row in securities),
            "active": sum(row.exchange == exchange and row.listing_status == "active" for row in securities),
            "missing_metadata": sum(row.exchange == exchange and (not row.name or not row.source_name) for row in securities),
        }
    index_rows = {}
    for symbol in EXPECTED_INDICES:
        rows = sorted((row for row in indices if row.symbol.upper() == symbol), key=lambda item: item.market_session_date, reverse=True)
        latest = rows[0] if rows else None
        index_rows[symbol] = {
            "available": latest is not None,
            "provider": latest.provider if latest else None,
            "latest_session": latest.market_session_date.isoformat() if latest else None,
            "last_retrieved": latest.retrieved_at.isoformat() if latest else None,
            "validation_status": latest.validation_status if latest else "unavailable",
            "missing_sessions": None,
            "note": "Missing sessions require an official exchange calendar; None means not inferred.",
        }
    financial_symbols = {row.security_id for row in financials}
    quarterly_symbols = {row.security_id for row in financials if row.period_type in {"quarter", "quarterly"}}
    annual_symbols = {row.security_id for row in financials if row.period_type in {"year", "annual"}}
    consolidated_symbols = {row.security_id for row in financials if row.statement_scope == "consolidated"}
    verified_symbols = {row.security_id for row in financials if row.verification_status == "verified"}
    latest_period = max((row.period_end for row in financials), default=None)
    return {
        "generated_at": generated_at,
        "market_data_mode": settings.market_data_mode,
        "securities": {
            "total": len(securities), "active": len(active), "suspended_or_delisted": len(stocks) - len(active),
            "by_exchange": exchange_counts,
            "missing_metadata": sum(not row.name or not row.source_name for row in securities),
        },
        "ohlcv": {
            "symbols_with_price": len(per_security),
            "active_symbols_with_latest_price": sum(row.id in latest_price_ids for row in active),
            "symbols_with_20_sessions": sum(len(rows) >= 20 for rows in per_security.values()),
            "symbols_with_50_sessions": sum(len(rows) >= 50 for rows in per_security.values()),
            "symbols_with_200_sessions": sum(len(rows) >= 200 for rows in per_security.values()),
            "stale_symbols": sum(security_id not in latest_price_ids for security_id in per_security),
            "validation_error_rows": price_validation_errors,
            "latest_session": latest_session,
            "latest_provider": latest_retrieved_row.provider if latest_retrieved_row else None,
            "latest_retrieved_at": latest_retrieved_row.ingested_at if latest_retrieved_row else None,
            "actual_trading_value_rows": actual_value,
            "market_cap_rows": market_cap,
            "foreign_flow_rows": foreign_flow,
            "foreign_flow_status": "unavailable: no persisted provider field",
            "staleness_note": "Four calendar days is a warning only; official trading-calendar confirmation is not inferred.",
        },
        "indices": index_rows,
        "financials": {
            "symbols_with_statements": len(financial_symbols),
            "symbols_with_quarterly": len(quarterly_symbols),
            "symbols_with_annual": len(annual_symbols),
            "symbols_with_consolidated": len(consolidated_symbols),
            "symbols_with_verified": len(verified_symbols),
            "latest_reporting_period": latest_period,
            "missing_periods": "not inferred without issuer reporting calendar",
        },
        "sources": [
            {"source_name": row.source_name, "status": row.status, "checked_at": row.checked_at, "last_success_at": row.last_success_at, "message": row.message}
            for row in health
        ],
        "provider_catalog": [item.model_dump(mode="json") for item in provider_catalog(settings)],
        "limitations": [
            "Coverage counts persisted rows and does not imply real-time or licensed full-market access.",
            "Fixture and authorized-file rows retain their provenance and are not upgraded to live data.",
            "Foreign flow and official missing-session counts remain unavailable until a provider/calendar is authorized.",
        ],
    }

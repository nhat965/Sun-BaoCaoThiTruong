"""Import OHLCV files that an operator is authorized to use.

The parser is deliberately strict: it never derives trading value from price and
volume, never downloads a source, and validates the declared market session against
the timestamp in the file. Database writes are delegated to ``PriceRepository`` so
the existing provider/session idempotency constraints remain authoritative.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.config import get_settings
from app.database import SessionLocal
from app.normalization import normalize_price_series
from app.repositories import PriceRepository, SecuritiesRepository
from app.schemas import (
    AuthorizedPriceImportResult,
    PriceBar,
    PriceSeries,
    Provenance,
)

REQUIRED_FIELDS = {
    "symbol",
    "trading_date",
    "market_timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "retrieved_at",
}


def _number(value: str, field: str) -> float:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return float(parsed)


def _integer(value: str, field: str) -> int:
    parsed = _number(value, field)
    if parsed < 0 or int(parsed) != parsed:
        raise ValueError(f"{field} must be a non-negative integer")
    return int(parsed)


def _timestamp(value: str, field: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(UTC)


def _declared_source_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source_url must be an HTTPS URL without embedded credentials")
    return url


def _parse_rows(
    content: str, source_name: str
) -> tuple[dict[tuple[str, str, str, bool, str | None, str], list[PriceBar]], list[str], datetime]:
    reader = csv.DictReader(StringIO(content.lstrip("\ufeff")))
    fields = {field.strip() for field in (reader.fieldnames or []) if field}
    missing = sorted(REQUIRED_FIELDS - fields)
    if missing:
        raise ValueError(f"CSV requires columns: {', '.join(missing)}")
    grouped: dict[tuple[str, str, str, bool], list[PriceBar]] = defaultdict(list)
    errors: list[str] = []
    retrieved_at: datetime | None = None
    settings = get_settings()
    for line_number, raw in enumerate(reader, start=2):
        try:
            symbol = (raw.get("symbol") or "").strip().upper()
            if not symbol.isalnum() or not 1 <= len(symbol) <= 16:
                raise ValueError("symbol must be 1-16 alphanumeric characters")
            timestamp = _timestamp(raw.get("market_timestamp", ""), "market_timestamp")
            declared_date = date.fromisoformat((raw.get("trading_date") or "").strip())
            session_date = timestamp.astimezone(ZoneInfo(settings.market_timezone)).date()
            if declared_date != session_date:
                raise ValueError(
                    f"trading_date {declared_date.isoformat()} does not match market_timestamp session {session_date.isoformat()}"
                )
            row_retrieved = _timestamp(raw.get("retrieved_at", ""), "retrieved_at")
            retrieved_at = row_retrieved if retrieved_at is None else max(retrieved_at, row_retrieved)
            source_url = _declared_source_url(raw.get("source_url"))
            provider = (raw.get("provider") or "authorized_file").strip()
            provider_id = (raw.get("provider_id") or "authorized_file").strip().lower()
            adjusted = (raw.get("adjusted") or "false").strip().lower() in {"1", "true", "yes"}
            status = (raw.get("validation_status") or "valid").strip().lower()
            if status not in {"valid", "partial"}:
                raise ValueError("validation_status must be valid or partial")
            bar = PriceBar(
                timestamp=timestamp,
                open=_number(raw.get("open", ""), "open"),
                high=_number(raw.get("high", ""), "high"),
                low=_number(raw.get("low", ""), "low"),
                close=_number(raw.get("close", ""), "close"),
                volume=_integer(raw.get("volume", ""), "volume"),
                actual_trading_value=(
                    _number(raw["actual_trading_value"], "actual_trading_value")
                    if raw.get("actual_trading_value")
                    else None
                ),
                market_cap=(
                    _number(raw["market_cap"], "market_cap") if raw.get("market_cap") else None
                ),
            )
            grouped[(symbol, provider, provider_id, adjusted, source_url, status)].append(bar)
        except (ValueError, ValidationError, TypeError) as exc:
            errors.append(f"line {line_number}: {exc}")
    return grouped, errors[:100], retrieved_at or datetime.now(UTC)


def preview_authorized_prices(content: str, source_name: str) -> AuthorizedPriceImportResult:
    grouped, errors, retrieved_at = _parse_rows(content, source_name)
    return AuthorizedPriceImportResult(
        inserted=0,
        updated=0,
        skipped=0,
        rejected=len(errors),
        symbols=sorted({key[0] for key in grouped}),
        source_name=source_name,
        validation_status="valid" if not errors else ("partial" if grouped else "rejected"),
        retrieved_at=retrieved_at,
        errors=errors,
    )


def import_authorized_prices(content: str, source_name: str) -> AuthorizedPriceImportResult:
    grouped, errors, retrieved_at = _parse_rows(content, source_name)
    inserted = updated = skipped = 0
    rejected = len(errors)
    symbols: set[str] = set()
    with SessionLocal() as session:
        securities = SecuritiesRepository(session)
        repository = PriceRepository(session)
        for (symbol, provider, provider_id, adjusted, source_url, validation_status), bars in grouped.items():
            security = securities.get(symbol)
            if security is None:
                rejected += len(bars)
                errors.append(f"{symbol}: security is not present in the securities master")
                continue
            try:
                provenance = Provenance(
                    source=provider,
                    provider_id=provider_id,
                    source_url=source_url,
                    provider_symbol=symbol,
                    retrieved_at=retrieved_at,
                    mode="authorized",
                    delayed=True,
                    validation_status=validation_status,
                    adjustment_policy="adjusted" if adjusted else "unadjusted",
                    coverage="security",
                    freshness="historical_or_delayed",
                    last_updated=retrieved_at,
                    notes=f"Authorized file import: {source_name}",
                )
                series = normalize_price_series(
                    PriceSeries(
                        security=security,
                        interval="1d",
                        adjusted=adjusted,
                        bars=bars,
                        provenance=provenance,
                    )
                )
                counts = repository.upsert_series_with_counts(series)
                inserted += counts.inserted
                updated += counts.updated
                skipped += counts.skipped
                symbols.add(symbol)
            except (ValueError, ValidationError) as exc:
                rejected += len(bars)
                errors.append(f"{symbol}: {exc}")
        session.commit()
    return AuthorizedPriceImportResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        rejected=rejected,
        symbols=sorted(symbols),
        source_name=source_name,
        validation_status="valid" if not errors else ("partial" if symbols else "rejected"),
        retrieved_at=retrieved_at,
        errors=errors[:100],
    )

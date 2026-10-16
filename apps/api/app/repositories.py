import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.analytics.fundamental import calculate_financial_metrics
from app.config import get_settings
from app.connectors.news import group_hash
from app.database import (
    AuditLogRecord,
    FinancialMetricRecord,
    FinancialPeriodRecord,
    FinancialStatementItemRecord,
    FinancialValidationReportRecord,
    NewsArticleRecord,
    NewsEventRecord,
    PriceObservation,
    SecurityRecord,
    SourceHealthRecord,
)
from app.financial_normalization import (
    MAPPING_VERSION,
    canonical_item_code,
    infer_period_start,
    normalize_currency,
    normalize_period_type,
)
from app.financial_validation import ValidationIssue, validate_period
from app.price_integrity import market_session_date, provider_id_for
from app.schemas import (
    FinancialInputs,
    FinancialMetricResult,
    FinancialStatementImportResult,
    FinancialStatementItem,
    FinancialStatementPeriod,
    FinancialStatementsResponse,
    FinancialTrendResponse,
    FinancialValidationReport,
    NewsItem,
    PriceBar,
    PriceSeries,
    Provenance,
    Security,
)
from app.text import normalize_vietnamese


def security_schema(row: SecurityRecord) -> Security:
    return Security(
        symbol=row.symbol,
        name=row.name,
        exchange=row.exchange,
        currency=row.currency,
        aliases=json.loads(row.aliases_json),
        industry=row.industry,
        sector=row.sector,
        listing_status=row.listing_status,
        security_type=row.security_type,
        provider_ids=json.loads(row.provider_ids_json),
        source_name=row.source_name,
        source_url=row.source_url,
        last_updated=row.last_updated,
    )


def comparable_financial_period(
    periods: list[FinancialPeriodRecord], current: FinancialPeriodRecord
) -> FinancialPeriodRecord | None:
    """Choose a like-for-like prior period; never compare adjacent incompatible quarters."""
    candidates = [
        period
        for period in periods
        if period.id != current.id
        and period.period_type == current.period_type
        and period.statement_scope == current.statement_scope
        and period.fiscal_year == current.fiscal_year - 1
    ]
    if current.period_type == "quarter":
        candidates = [
            period
            for period in candidates
            if period.fiscal_quarter == current.fiscal_quarter
        ]
    return max(
        candidates,
        key=lambda period: (
            period.period_end,
            period.statement_status == "amended",
            period.verification_status == "verified",
            period.updated_at,
        ),
        default=None,
    )


class SecuritiesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, symbol: str, include_inactive: bool = True) -> Security | None:
        query = select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        if not include_inactive:
            query = query.where(SecurityRecord.listing_status == "active")
        row = self.session.scalar(query)
        return security_schema(row) if row else None

    def search(self, query: str, limit: int = 20, include_inactive: bool = False) -> list[Security]:
        normalized = normalize_vietnamese(query)
        statement = select(SecurityRecord)
        if not include_inactive:
            statement = statement.where(SecurityRecord.listing_status == "active")
        if normalized:
            pattern = f"%{normalized}%"
            statement = statement.where(
                or_(
                    func.lower(SecurityRecord.symbol).like(pattern),
                    SecurityRecord.normalized_name.like(pattern),
                    func.lower(SecurityRecord.aliases_json).like(pattern),
                )
            )
        rows = self.session.scalars(
            statement.order_by(SecurityRecord.symbol).limit(limit)
        ).all()
        return [security_schema(row) for row in rows]

    def upsert(self, security: Security) -> tuple[Security, bool]:
        row = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == security.symbol.upper())
        )
        inserted = row is None
        if row is None:
            row = SecurityRecord(symbol=security.symbol.upper())
            self.session.add(row)
        if security.name.strip():
            row.name = security.name
            row.normalized_name = normalize_vietnamese(security.name)
        if security.aliases:
            row.aliases_json = json.dumps(security.aliases, ensure_ascii=False)
        row.exchange = security.exchange.upper() or row.exchange
        # A provider response is allowed to omit optional taxonomy fields. Do
        # not erase a richer existing classification with nulls during replay.
        if security.industry is not None:
            row.industry = security.industry
        if security.sector is not None:
            row.sector = security.sector
        row.listing_status = security.listing_status
        row.security_type = security.security_type
        try:
            existing_provider_ids = json.loads(row.provider_ids_json or "{}")
        except (TypeError, ValueError):
            existing_provider_ids = {}
        if not isinstance(existing_provider_ids, dict):
            existing_provider_ids = {}
        existing_provider_ids.update(security.provider_ids)
        row.provider_ids_json = json.dumps(existing_provider_ids)
        row.source_name = security.source_name or row.source_name or "user-authorized-import"
        if security.source_url is not None:
            row.source_url = security.source_url
        row.last_updated = security.last_updated or datetime.now(UTC)
        if security.currency:
            row.currency = security.currency
        self.session.flush()
        return security_schema(row), inserted


@dataclass(frozen=True)
class IngestionCounts:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def persisted_series(self, symbol: str, limit: int = 260) -> PriceSeries | None:
        """Return the latest persisted OHLCV series for a security.

        This is deliberately a read-only fallback for analysis when an upstream
        provider is unavailable.  It selects one provider/interval/adjustment
        stream and retains the source metadata stored with each observation.
        No values are synthesized or recalculated here.
        """
        security_row = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security_row is None:
            return None
        latest = self.session.scalar(
            select(PriceObservation)
            .where(PriceObservation.security_id == security_row.id)
            .order_by(
                PriceObservation.market_timestamp.desc(),
                PriceObservation.ingested_at.desc(),
                PriceObservation.id.desc(),
            )
        )
        if latest is None:
            return None
        rows = list(
            self.session.scalars(
                select(PriceObservation)
                .where(
                    PriceObservation.security_id == security_row.id,
                    PriceObservation.provider_id == latest.provider_id,
                    PriceObservation.interval == latest.interval,
                    PriceObservation.adjusted == latest.adjusted,
                )
                .order_by(PriceObservation.market_timestamp.desc(), PriceObservation.id.desc())
                .limit(limit)
            ).all()
        )
        if not rows:
            return None
        rows.reverse()

        def as_utc(value: datetime | None) -> datetime | None:
            if value is None or value.tzinfo is not None:
                return value
            # SQLite drops timezone metadata even though ingestion stores UTC.
            return value.replace(tzinfo=UTC)

        bars = [
            PriceBar(
                timestamp=as_utc(row.market_timestamp),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
                actual_trading_value=(
                    float(row.actual_trading_value)
                    if row.actual_trading_value is not None
                    else None
                ),
                market_cap=float(row.market_cap) if row.market_cap is not None else None,
            )
            for row in rows
        ]
        latest = rows[-1]
        mode = latest.source_mode if latest.source_mode in {"live", "fixture", "authorized"} else "unknown"
        return PriceSeries(
            security=security_schema(security_row),
            interval=latest.interval,
            adjusted=latest.adjusted,
            bars=bars,
            provenance=Provenance(
                source=latest.provider,
                provider_id=latest.provider_id,
                source_url=latest.source_url,
                provider_symbol=latest.provider_symbol,
                retrieved_at=max(as_utc(row.ingested_at) for row in rows),
                market_timestamp=as_utc(latest.market_timestamp),
                mode=mode,
                delayed=True,
                validation_status=(
                    "valid"
                    if all(row.validation_status == "valid" for row in rows)
                    else "partial"
                ),
                adjustment_policy=latest.adjustment_policy,
                coverage=latest.coverage,
                freshness="historical",
                last_updated=max(
                    (as_utc(row.last_updated) or as_utc(row.ingested_at)) for row in rows
                ),
                notes=(
                    "Served from persisted observations after the configured upstream "
                    "provider failed; this response is historical/delayed, not realtime."
                ),
            ),
        )

    def upsert_series(self, series: PriceSeries) -> int:
        return self.upsert_series_with_counts(series).inserted

    def upsert_series_with_counts(self, series: PriceSeries) -> IngestionCounts:
        security_row = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == series.security.symbol)
        )
        if security_row is None:
            raise ValueError("Security must exist before storing prices")
        if series.security.currency.upper() != security_row.currency.upper():
            raise ValueError(
                f"Price currency {series.security.currency} does not match "
                f"securities master currency {security_row.currency}"
            )
        inserted = updated = skipped = 0
        previous = None
        settings = get_settings()
        provider_id = provider_id_for(
            series.provenance.source, series.provenance.provider_id
        )
        for bar in series.bars:
            quality_flags = []
            if bar.volume == 0:
                quality_flags.append("zero_volume")
            if previous is not None:
                if abs(bar.close / previous.close - 1) > 0.2:
                    quality_flags.append("price_jump_over_20_percent")
                if (bar.timestamp.date() - previous.timestamp.date()).days > 4:
                    quality_flags.append("calendar_gap_over_4_days")
            session_date = market_session_date(bar.timestamp, settings.market_timezone)
            values = {
                "security_id": security_row.id,
                "provider": series.provenance.source,
                "provider_id": provider_id,
                "provider_symbol": series.provenance.provider_symbol,
                "market_timestamp": bar.timestamp,
                "market_session_date": session_date,
                "ingested_at": series.provenance.retrieved_at,
                "interval": series.interval,
                "open": Decimal(str(bar.open)),
                "high": Decimal(str(bar.high)),
                "low": Decimal(str(bar.low)),
                "close": Decimal(str(bar.close)),
                "volume": bar.volume,
                "actual_trading_value": (
                    Decimal(str(bar.actual_trading_value))
                    if bar.actual_trading_value is not None
                    else None
                ),
                "market_cap": (
                    Decimal(str(bar.market_cap)) if bar.market_cap is not None else None
                ),
                "currency": series.security.currency,
                "adjusted": series.adjusted,
                "validation_status": series.provenance.validation_status,
                "adjustment_policy": series.provenance.adjustment_policy,
                "quality_flags_json": json.dumps(quality_flags),
                "source_mode": series.provenance.mode,
                "source_url": series.provenance.source_url,
                "coverage": series.provenance.coverage,
                "freshness": series.provenance.freshness,
                "last_updated": series.provenance.last_updated or series.provenance.retrieved_at,
            }
            existing = self.session.scalar(
                select(PriceObservation).where(
                    PriceObservation.security_id == security_row.id,
                    PriceObservation.provider_id == provider_id,
                    PriceObservation.market_session_date == session_date,
                    PriceObservation.interval == series.interval,
                    PriceObservation.adjusted == series.adjusted,
                )
            )
            if existing is None:
                self.session.add(PriceObservation(**values))
                inserted += 1
            elif (
                existing.validation_status == "valid"
                and series.provenance.validation_status != "valid"
            ):
                skipped += 1
            else:
                material_keys = {
                    "provider",
                    "provider_id",
                    "provider_symbol",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "actual_trading_value",
                    "market_cap",
                    "currency",
                    "adjusted",
                    "validation_status",
                    "adjustment_policy",
                    "quality_flags_json",
                    "source_mode",
                    "source_url",
                    "coverage",
                    "freshness",
                }
                unchanged = all(
                    getattr(existing, key) == value
                    for key, value in values.items()
                    if key in material_keys
                )
                if unchanged:
                    skipped += 1
                else:
                    for key, value in values.items():
                        setattr(existing, key, value)
                    updated += 1
            previous = bar
        self.session.flush()
        return IngestionCounts(inserted=inserted, updated=updated, skipped=skipped)


class AuditRepository:
    def __init__(self, session):
        self.session = session

    def record(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        source_ip: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.session.add(
            AuditLogRecord(
                actor=actor,
                action=action,
                resource=resource,
                outcome=outcome,
                source_ip=source_ip,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
                created_at=datetime.now(UTC),
            )
        )


class SourceHealthRepository:
    def __init__(self, session):
        self.session = session

    def record(
        self,
        source_name: str,
        *,
        status: str,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        checked_at = datetime.now(UTC)
        current = self.session.scalar(
            select(SourceHealthRecord).where(SourceHealthRecord.source_name == source_name)
        )
        if current is None:
            current = SourceHealthRecord(
                source_name=source_name,
                status=status,
                checked_at=checked_at,
                latency_ms=latency_ms,
                message=message,
                consecutive_failures=0 if status == "available" else 1,
                last_success_at=checked_at if status == "available" else None,
                last_failure_at=checked_at if status != "available" else None,
            )
            self.session.add(current)
        else:
            current.status = status
            current.checked_at = checked_at
            current.latency_ms = latency_ms
            current.message = message
            current.consecutive_failures = (
                0 if status == "available" else current.consecutive_failures + 1
            )
            if status == "available":
                current.last_success_at = checked_at
            else:
                current.last_failure_at = checked_at


FINANCIAL_STATEMENT_TYPES = {"income", "balance", "cash_flow"}
FINANCIAL_PERIOD_TYPES = {"quarter", "year", "ytd", "ttm"}
FINANCIAL_STATEMENT_SCOPES = {"consolidated", "separate"}
FINANCIAL_STATEMENT_STATUSES = {"original", "amended"}
FINANCIAL_VERIFICATION_STATUSES = {"verified", "unverified", "rejected"}
FINANCIAL_UNIT_MULTIPLIERS = {
    "VND": (Decimal(1), "VND"),
    "THOUSAND_VND": (Decimal(1000), "VND"),
    "MILLION_VND": (Decimal(1000000), "VND"),
    "BILLION_VND": (Decimal(1000000000), "VND"),
    "SHARES": (Decimal(1), "shares"),
    "RATIO": (Decimal(1), "ratio"),
}


def _entity_type(security: SecurityRecord) -> str:
    text = f"{security.sector or ''} {security.industry or ''}".lower()
    if "ngân hàng" in text or "bank" in text:
        return "bank"
    if "chứng khoán" in text or "securities" in text:
        return "securities"
    if "bảo hiểm" in text or "insurance" in text:
        return "insurance"
    return "non_financial"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.strip())
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class FinancialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_csv(
        self,
        symbol: str,
        content: str,
        default_source: str,
        *,
        strict: bool = False,
        accept_verified_status: bool = True,
    ) -> FinancialStatementImportResult:
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        inserted_periods = updated_periods = inserted_items = updated_items = rejected = 0
        skipped_items = 0
        errors: list[str] = []
        import_warnings: list[str] = []
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        retrieved_at_default = datetime.now(UTC)
        seen_periods: set[tuple[datetime, str, str]] = set()
        seen_items: set[tuple[datetime, str, str, str, str]] = set()
        touched_period_ids: set[int] = set()
        reader = csv.DictReader(StringIO(content))
        required = {
            "period_end",
            "period_type",
            "fiscal_year",
            "statement_type",
            "item_code",
            "value",
        }
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"CSV BCTC thiếu cột bắt buộc: {sorted(required)}")
        for line_number, row in enumerate(reader, start=2):
            try:
                period_end = _parse_datetime(row.get("period_end"))
                if period_end is None:
                    raise ValueError("period_end is required")
                period_type = normalize_period_type(row.get("period_type") or "")
                statement_scope = (row.get("statement_scope") or "consolidated").strip().lower()
                statement_status = (row.get("statement_status") or "original").strip().lower()
                statement_type = (row.get("statement_type") or "").strip().lower()
                raw_item_code = (row.get("item_code") or "").strip()
                item_code = canonical_item_code(raw_item_code)
                if period_type not in FINANCIAL_PERIOD_TYPES:
                    raise ValueError(f"period_type must be one of {sorted(FINANCIAL_PERIOD_TYPES)}")
                if statement_type not in FINANCIAL_STATEMENT_TYPES:
                    raise ValueError(
                        f"statement_type must be one of {sorted(FINANCIAL_STATEMENT_TYPES)}"
                    )
                if statement_scope not in FINANCIAL_STATEMENT_SCOPES:
                    raise ValueError(
                        f"statement_scope must be one of {sorted(FINANCIAL_STATEMENT_SCOPES)}"
                    )
                if statement_status not in FINANCIAL_STATEMENT_STATUSES:
                    raise ValueError(
                        f"statement_status must be one of {sorted(FINANCIAL_STATEMENT_STATUSES)}"
                    )
                if len(raw_item_code) > 128 or len(item_code) > 64:
                    raise ValueError("item_code is required and must be <= 64 characters")
                raw_value = Decimal((row.get("value") or "").strip())
                raw_unit = (row.get("unit") or "VND").strip().upper()
                if raw_unit not in FINANCIAL_UNIT_MULTIPLIERS:
                    raise ValueError(
                        "unit must be one of "
                        f"{sorted(FINANCIAL_UNIT_MULTIPLIERS)}"
                    )
                multiplier, normalized_unit = FINANCIAL_UNIT_MULTIPLIERS[raw_unit]
                value = raw_value * multiplier
                row_currency = normalize_currency(row.get("currency"))
                if normalized_unit == "VND" and row_currency != "VND":
                    raise ValueError(
                        "currency must be VND when the declared unit is a VND scale"
                    )
                verification_status = (
                    row.get("verification_status") or "unverified"
                ).strip().lower()
                if verification_status not in FINANCIAL_VERIFICATION_STATUSES:
                    raise ValueError(
                        "verification_status must be one of "
                        f"{sorted(FINANCIAL_VERIFICATION_STATUSES)}"
                    )
                if verification_status == "verified" and not accept_verified_status:
                    verification_status = "unverified"
                    import_warnings.append(
                        "Automated retrieval does not grant verified status; stored as unverified."
                    )
                fiscal_year = int((row.get("fiscal_year") or "").strip())
                quarter_text = (row.get("fiscal_quarter") or "").strip()
                fiscal_quarter = int(quarter_text) if quarter_text else None
                if fiscal_quarter is not None and fiscal_quarter not in {1, 2, 3, 4}:
                    raise ValueError("fiscal_quarter must be 1-4")
                period_start = infer_period_start(
                    period_end,
                    period_type,
                    fiscal_year,
                    fiscal_quarter,
                    _parse_datetime(row.get("period_start")),
                )
                accounting_standard = (
                    row.get("accounting_standard") or "unknown"
                ).strip().lower()[:32]
                data_version = (row.get("data_version") or "financial-v1").strip()[:32]
                row_retrieved_at = _parse_datetime(row.get("retrieved_at"))
                retrieved_at = row_retrieved_at or retrieved_at_default
                period = self.session.scalar(
                    select(FinancialPeriodRecord).where(
                        FinancialPeriodRecord.security_id == security.id,
                        FinancialPeriodRecord.period_end == period_end,
                        FinancialPeriodRecord.period_type == period_type,
                        FinancialPeriodRecord.statement_scope == statement_scope,
                        FinancialPeriodRecord.statement_status == statement_status,
                    )
                )
                source_name = (row.get("source_name") or default_source).strip()[:128]
                if period is None:
                    period = FinancialPeriodRecord(
                        security_id=security.id,
                        period_start=period_start,
                        period_end=period_end,
                        period_type=period_type,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        reported_at=_parse_datetime(row.get("reported_at")),
                        source_name=source_name,
                        source_url=(row.get("source_url") or None),
                        verification_status=verification_status,
                        statement_scope=statement_scope,
                        statement_status=statement_status,
                        accounting_standard=accounting_standard,
                        unit="VND" if normalized_unit == "VND" else normalized_unit,
                        currency=row_currency,
                        retrieved_at=retrieved_at,
                        validated_at=None,
                        data_version=data_version,
                        content_hash=content_hash,
                        updated_at=datetime.now(UTC),
                    )
                    self.session.add(period)
                    self.session.flush()
                    inserted_periods += 1
                else:
                    may_update_period = not (
                        period.verification_status == "verified"
                        and verification_status != "verified"
                    )
                    period_source_url = row.get("source_url") or period.source_url
                    period_unit = "VND" if normalized_unit == "VND" else normalized_unit
                    period_currency = row_currency if row.get("currency") else period.currency
                    if period.unit == "VND" and period_currency != "VND":
                        raise ValueError(
                            "currency must remain VND for a VND-denominated period"
                        )
                    period_changed = may_update_period and any(
                        (
                            period.source_name != source_name,
                            period.source_url != period_source_url,
                            period.verification_status != verification_status,
                            period.unit != period_unit,
                            period.currency != period_currency,
                            period.fiscal_year != fiscal_year,
                            period.fiscal_quarter != fiscal_quarter,
                            period.period_start != period_start,
                            period.accounting_standard != accounting_standard,
                            period.data_version != data_version,
                            period.content_hash != content_hash,
                            row_retrieved_at is not None
                            and period.retrieved_at != row_retrieved_at,
                        )
                    )
                    if period_changed:
                        period.source_name = source_name
                        period.source_url = period_source_url
                        period.verification_status = verification_status
                        period.unit = period_unit
                        period.currency = period_currency
                        period.fiscal_year = fiscal_year
                        period.fiscal_quarter = fiscal_quarter
                        period.period_start = period_start
                        period.accounting_standard = accounting_standard
                        period.data_version = data_version
                        period.content_hash = content_hash
                        if row_retrieved_at is not None:
                            period.retrieved_at = row_retrieved_at
                        period.updated_at = datetime.now(UTC)
                    period_key = (
                        period_end,
                        f"{period_type}:{statement_scope}",
                        statement_status,
                    )
                    if period_changed and period_key not in seen_periods:
                        updated_periods += 1
                seen_periods.add(
                    (period_end, f"{period_type}:{statement_scope}", statement_status)
                )
                touched_period_ids.add(period.id)
                item_key = (
                    period_end,
                    period_type,
                    statement_scope,
                    statement_status,
                    f"{statement_type}:{item_code}",
                )
                if item_key in seen_items:
                    raise ValueError("duplicate financial item in the same CSV batch")
                seen_items.add(item_key)
                item = self.session.scalar(
                    select(FinancialStatementItemRecord).where(
                        FinancialStatementItemRecord.period_id == period.id,
                        FinancialStatementItemRecord.statement_type == statement_type,
                        FinancialStatementItemRecord.item_code == item_code,
                    )
                )
                if item is None:
                    self.session.add(
                        FinancialStatementItemRecord(
                            period_id=period.id,
                            statement_type=statement_type,
                            item_code=item_code,
                            raw_item_code=raw_item_code,
                            mapping_version=MAPPING_VERSION,
                            value=value,
                            unit=normalized_unit,
                            raw_value=raw_value,
                            raw_unit=raw_unit,
                            source_name=source_name,
                            source_url=row.get("source_url") or None,
                            verification_status=verification_status,
                            updated_at=datetime.now(UTC),
                        )
                    )
                    inserted_items += 1
                else:
                    if (
                        item.verification_status == "verified"
                        and verification_status != "verified"
                    ):
                        skipped_items += 1
                    else:
                        item_source_url = row.get("source_url") or item.source_url
                        item_changed = any(
                            (
                                item.value != value,
                                item.unit != normalized_unit,
                                item.raw_value != raw_value,
                                item.raw_unit != raw_unit,
                                item.source_name != source_name,
                                item.source_url != item_source_url,
                                item.verification_status != verification_status,
                                item.raw_item_code != raw_item_code,
                                item.mapping_version != MAPPING_VERSION,
                            )
                        )
                        if item_changed:
                            item.value = value
                            item.unit = normalized_unit
                            item.raw_value = raw_value
                            item.raw_unit = raw_unit
                            item.source_name = source_name
                            item.source_url = item_source_url
                            item.verification_status = verification_status
                            item.raw_item_code = raw_item_code
                            item.mapping_version = MAPPING_VERSION
                            item.updated_at = datetime.now(UTC)
                            updated_items += 1
                        else:
                            skipped_items += 1
            except (ArithmeticError, TypeError, ValueError) as exc:
                rejected += 1
                errors.append(f"line {line_number}: {exc}")
        self.session.flush()
        validation_reports: list[FinancialValidationReport] = []
        serious_validation_error = False
        created_at = datetime.now(UTC)
        for period_id in sorted(touched_period_ids):
            period = self.session.get(FinancialPeriodRecord, period_id)
            if period is None:
                continue
            period_items = list(
                self.session.scalars(
                    select(FinancialStatementItemRecord).where(
                        FinancialStatementItemRecord.period_id == period_id
                    )
                )
            )
            values = {item.item_code: Decimal(item.value) for item in period_items}
            validation = validate_period(
                period_type=period.period_type,
                period_start=period.period_start,
                period_end=period.period_end,
                reported_at=period.reported_at,
                currency=period.currency,
                statement_scope=period.statement_scope,
                statement_status=period.statement_status,
                source_name=period.source_name,
                source_url=period.source_url,
                values=values,
            )
            issues = list(validation.issues)
            issues.extend(
                ValidationIssue(
                    code="import_warning",
                    severity="warning",
                    message=warning,
                    source_name=period.source_name,
                )
                for warning in dict.fromkeys(import_warnings)
            )
            report_errors = [issue.message for issue in issues if issue.severity == "error"]
            report_warnings = [
                issue.message for issue in issues if issue.severity == "warning"
            ]
            status = "invalid" if report_errors else validation.status
            serious_validation_error = serious_validation_error or bool(report_errors)
            validation_reports.append(
                FinancialValidationReport(
                    symbol=security.symbol,
                    period_end=period.period_end,
                    period_type=period.period_type,
                    statement_scope=period.statement_scope,
                    statement_status=period.statement_status,
                    source_name=period.source_name,
                    source_url=period.source_url,
                    checks=validation.checks,
                    errors=report_errors,
                    warnings=report_warnings,
                    validation_status=status,
                    issues=[issue.__dict__ for issue in issues],
                    created_at=created_at,
                )
            )
            errors.extend(
                f"{period.period_end.date()} {period.statement_scope}/{period.statement_status}: {message}"
                for message in report_errors
            )
            rejected += len(report_errors)

        rolled_back = serious_validation_error or (strict and rejected > 0)
        if rolled_back:
            self.session.rollback()
            inserted_periods = updated_periods = inserted_items = updated_items = 0
            skipped_items = 0
        for report in validation_reports:
            self.session.add(
                FinancialValidationReportRecord(
                    security_id=security.id,
                    period_id=None if rolled_back else next(
                        (
                            period_id
                            for period_id in touched_period_ids
                            if (
                                (period := self.session.get(FinancialPeriodRecord, period_id))
                                and period.period_end == report.period_end
                                and period.period_type == report.period_type
                                and period.statement_scope == report.statement_scope
                                and period.statement_status == report.statement_status
                            )
                        ),
                        None,
                    ),
                    period_end=report.period_end,
                    period_type=report.period_type,
                    statement_scope=report.statement_scope,
                    statement_status=report.statement_status,
                    source_name=report.source_name,
                    source_url=report.source_url,
                    checks_json=json.dumps(report.checks),
                    issues_json=json.dumps(
                        [issue.model_dump() for issue in report.issues],
                        ensure_ascii=False,
                    ),
                    errors_json=json.dumps(report.errors),
                    warnings_json=json.dumps(report.warnings),
                    validation_status=report.validation_status,
                    created_at=report.created_at,
                )
            )
        self.session.commit()
        return FinancialStatementImportResult(
            inserted_periods=inserted_periods,
            updated_periods=updated_periods,
            inserted_items=inserted_items,
            updated_items=updated_items,
            skipped_items=skipped_items,
            rejected=rejected,
            errors=errors[:100],
            validation_reports=validation_reports,
        )

    def statements(
        self,
        symbol: str,
        *,
        period_type: str | None = None,
        statement_scope: str | None = None,
        limit: int = 12,
    ) -> FinancialStatementsResponse:
        if period_type and period_type not in FINANCIAL_PERIOD_TYPES:
            raise ValueError(f"period_type must be one of {sorted(FINANCIAL_PERIOD_TYPES)}")
        if statement_scope and statement_scope not in FINANCIAL_STATEMENT_SCOPES:
            raise ValueError(
                f"statement_scope must be one of {sorted(FINANCIAL_STATEMENT_SCOPES)}"
            )
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        statement = select(FinancialPeriodRecord).where(
            FinancialPeriodRecord.security_id == security.id
        )
        if period_type:
            statement = statement.where(FinancialPeriodRecord.period_type == period_type)
        if statement_scope:
            statement = statement.where(
                FinancialPeriodRecord.statement_scope == statement_scope
            )
        periods = list(
            self.session.scalars(
                statement.order_by(FinancialPeriodRecord.period_end.desc()).limit(limit)
            )
        )
        payload = []
        for period in periods:
            rows = list(
                self.session.scalars(
                    select(FinancialStatementItemRecord)
                    .where(FinancialStatementItemRecord.period_id == period.id)
                    .order_by(
                        FinancialStatementItemRecord.statement_type,
                        FinancialStatementItemRecord.item_code,
                    )
                )
            )
            payload.append(
                FinancialStatementPeriod(
                    period_start=period.period_start,
                    period_end=period.period_end,
                    period_type=period.period_type,
                    fiscal_year=period.fiscal_year,
                    fiscal_quarter=period.fiscal_quarter,
                    reported_at=period.reported_at,
                    statement_scope=period.statement_scope,
                    statement_status=period.statement_status,
                    accounting_standard=period.accounting_standard,
                    currency=period.currency,
                    source_name=period.source_name,
                    source_url=period.source_url,
                    verification_status=period.verification_status,
                    retrieved_at=period.retrieved_at,
                    validated_at=period.validated_at,
                    data_version=period.data_version,
                    content_hash=period.content_hash,
                    updated_at=period.updated_at,
                    items=[
                        FinancialStatementItem(
                            statement_type=row.statement_type,
                            item_code=row.item_code,
                            raw_item_code=row.raw_item_code,
                            mapping_version=row.mapping_version,
                            value=float(row.value),
                            unit=row.unit,
                            raw_value=(
                                float(row.raw_value) if row.raw_value is not None else None
                            ),
                            raw_unit=row.raw_unit,
                            source_name=row.source_name,
                            source_url=row.source_url,
                            verification_status=row.verification_status,
                            updated_at=row.updated_at,
                        )
                        for row in rows
                    ],
                )
            )
        return FinancialStatementsResponse(
            symbol=security.symbol,
            automatic_sync_status="blocked",
            automatic_sync_message=(
                "BLOCKED: chưa có provider BCTC được cấp quyền và gọi thành công; "
                "dữ liệu hiện tại chỉ đến từ file được phép."
            ),
            periods=payload,
        )

    def validation_reports(
        self, symbol: str, *, limit: int = 50
    ) -> list[FinancialValidationReport]:
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        rows = self.session.scalars(
            select(FinancialValidationReportRecord)
            .where(FinancialValidationReportRecord.security_id == security.id)
            .order_by(FinancialValidationReportRecord.created_at.desc())
            .limit(limit)
        ).all()
        return [
            FinancialValidationReport(
                symbol=security.symbol,
                period_end=row.period_end,
                period_type=row.period_type,
                statement_scope=row.statement_scope,
                statement_status=row.statement_status,
                source_name=row.source_name,
                source_url=row.source_url,
                checks=json.loads(row.checks_json),
                errors=json.loads(row.errors_json),
                warnings=json.loads(row.warnings_json),
                validation_status=row.validation_status,
                issues=json.loads(getattr(row, "issues_json", "[]")),
                created_at=row.created_at,
            )
            for row in rows
        ]

    def calculate_latest(self, symbol: str) -> FinancialMetricResult:
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        periods = list(
            self.session.scalars(
                select(FinancialPeriodRecord)
                .where(FinancialPeriodRecord.security_id == security.id)
                .order_by(
                    FinancialPeriodRecord.period_end.desc(),
                    case((FinancialPeriodRecord.statement_status == "amended", 0), else_=1),
                    case((FinancialPeriodRecord.verification_status == "verified", 0), else_=1),
                    FinancialPeriodRecord.updated_at.desc(),
                )
            )
        )
        if not periods:
            raise LookupError(f"Chưa có dữ liệu BCTC cho {security.symbol}.")
        current = next(
            (period for period in periods if period.statement_scope == "consolidated"), periods[0]
        )
        previous = comparable_financial_period(periods, current)
        sequential_candidates = [
            period
            for period in periods
            if period.period_type == current.period_type
            and period.statement_scope == current.statement_scope
            and period.period_end < current.period_end
        ]
        previous_sequential = max(
            sequential_candidates, key=lambda period: period.period_end, default=None
        )

        def values(period: FinancialPeriodRecord | None) -> dict[str, float]:
            if period is None:
                return {}
            rows = self.session.scalars(
                select(FinancialStatementItemRecord).where(
                    FinancialStatementItemRecord.period_id == period.id
                )
            )
            return {row.item_code: float(row.value) for row in rows}

        current_values = values(current)
        previous_values = values(previous)
        sequential_values = values(previous_sequential)
        quarter_window = []
        if current.period_type == "quarter":
            seen_quarters = set()
            for period in sorted(
                (
                    item
                    for item in periods
                    if item.period_type == "quarter"
                    and item.statement_scope == current.statement_scope
                    and item.period_end <= current.period_end
                ),
                key=lambda item: (
                    item.period_end,
                    item.statement_status == "amended",
                    item.updated_at,
                ),
                reverse=True,
            ):
                key = (period.fiscal_year, period.fiscal_quarter)
                if key not in seen_quarters:
                    seen_quarters.add(key)
                    quarter_window.append(values(period))
                if len(quarter_window) == 4:
                    break

        def ttm(item_code: str) -> float | None:
            values_for_item = [item.get(item_code) for item in quarter_window]
            return (
                sum(value for value in values_for_item if value is not None)
                if len(values_for_item) == 4 and all(value is not None for value in values_for_item)
                else None
            )
        with_price = self.session.scalar(
            select(PriceObservation.close)
            .join(SecurityRecord, PriceObservation.security_id == SecurityRecord.id)
            .where(SecurityRecord.id == security.id)
            .order_by(PriceObservation.market_timestamp.desc())
        )
        inputs = FinancialInputs(
            entity_type=_entity_type(security),
            revenue=current_values.get("revenue"),
            prior_revenue=previous_values.get("revenue"),
            previous_period_revenue=sequential_values.get("revenue"),
            ttm_revenue=ttm("revenue"),
            net_income=current_values.get("net_income"),
            net_income_attributable_to_parent=current_values.get(
                "net_income_attributable_to_parent"
            ),
            prior_net_income=previous_values.get("net_income"),
            previous_period_net_income=sequential_values.get("net_income"),
            ttm_net_income=ttm("net_income"),
            period_months=3 if current.period_type == "quarter" else 12,
            total_assets=current_values.get("total_assets"),
            prior_total_assets=previous_values.get("total_assets"),
            total_equity=current_values.get("total_equity"),
            prior_total_equity=previous_values.get("total_equity"),
            total_debt=current_values.get("total_debt"),
            prior_total_debt=previous_values.get("total_debt"),
            cash_and_equivalents=current_values.get("cash_and_equivalents"),
            prior_cash_and_equivalents=previous_values.get("cash_and_equivalents"),
            current_assets=current_values.get("current_assets"),
            inventory=current_values.get("inventory"),
            current_liabilities=current_values.get("current_liabilities"),
            operating_income=current_values.get("operating_income"),
            profit_before_tax=current_values.get("profit_before_tax"),
            tax_expense=current_values.get("tax_expense"),
            gross_profit=current_values.get("gross_profit"),
            interest_expense=current_values.get("interest_expense"),
            operating_cash_flow=current_values.get("operating_cash_flow"),
            ttm_operating_cash_flow=ttm("operating_cash_flow"),
            capital_expenditure=current_values.get("capital_expenditure"),
            ttm_capital_expenditure=ttm("capital_expenditure"),
            shares_outstanding=current_values.get("shares_outstanding"),
            diluted_shares_outstanding=current_values.get("weighted_average_shares"),
            market_price=float(with_price) if with_price is not None else None,
            enterprise_value=current_values.get("enterprise_value"),
            ebitda=current_values.get("ebitda"),
        )
        result = calculate_financial_metrics(inputs)
        calculated_at = result.calculated_at
        for metric_name, value in result.metrics.items():
            metric = self.session.scalar(
                select(FinancialMetricRecord).where(
                    FinancialMetricRecord.security_id == security.id,
                    FinancialMetricRecord.period_id == current.id,
                    FinancialMetricRecord.metric_name == metric_name,
                )
            )
            if metric is None:
                self.session.add(
                    FinancialMetricRecord(
                        security_id=security.id,
                        period_id=current.id,
                        metric_name=metric_name,
                        value=None if value is None else Decimal(str(value)),
                        formula_version=result.formula_version,
                        source_name=current.source_name,
                        calculated_at=calculated_at,
                    )
                )
            else:
                metric.value = None if value is None else Decimal(str(value))
                metric.formula_version = result.formula_version
                metric.source_name = current.source_name
                metric.calculated_at = calculated_at
        self.session.commit()
        metric_metadata = {
            code: metadata.model_copy(update={"as_of_date": current.period_end})
            for code, metadata in result.metric_metadata.items()
        }
        return result.model_copy(
            update={
                "symbol": security.symbol,
                "period_type": current.period_type,
                "period_end": current.period_end,
                "source_name": current.source_name,
                "statement_scope": current.statement_scope,
                "statement_status": current.statement_status,
                "metric_metadata": metric_metadata,
            }
        )

    def history(
        self,
        symbol: str,
        *,
        period_type: str = "year",
        statement_scope: str = "consolidated",
        limit: int = 8,
    ) -> FinancialTrendResponse:
        if period_type not in FINANCIAL_PERIOD_TYPES:
            raise ValueError(f"period_type must be one of {sorted(FINANCIAL_PERIOD_TYPES)}")
        if statement_scope not in FINANCIAL_STATEMENT_SCOPES:
            raise ValueError(
                f"statement_scope must be one of {sorted(FINANCIAL_STATEMENT_SCOPES)}"
            )
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        periods = list(
            self.session.scalars(
                select(FinancialPeriodRecord)
                .where(
                    FinancialPeriodRecord.security_id == security.id,
                    FinancialPeriodRecord.period_type == period_type,
                    FinancialPeriodRecord.statement_scope == statement_scope,
                )
                .order_by(FinancialPeriodRecord.period_end.asc())
            )
        )
        latest_versions: dict[tuple[datetime, str, str], FinancialPeriodRecord] = {}
        for period in periods:
            key = (period.period_end, period.period_type, period.statement_scope)
            current = latest_versions.get(key)
            if current is None or (
                period.statement_status == "amended",
                period.verification_status == "verified",
                period.updated_at,
            ) > (
                current.statement_status == "amended",
                current.verification_status == "verified",
                current.updated_at,
            ):
                latest_versions[key] = period
        periods = sorted(latest_versions.values(), key=lambda item: item.period_end)
        if not periods:
            raise LookupError(
                f"Chưa có BCTC {statement_scope}/{period_type} cho {security.symbol}."
            )

        def values(period: FinancialPeriodRecord | None) -> dict[str, float]:
            if period is None:
                return {}
            rows = self.session.scalars(
                select(FinancialStatementItemRecord).where(
                    FinancialStatementItemRecord.period_id == period.id
                )
            )
            return {row.item_code: float(row.value) for row in rows}

        selected = periods[-limit:]
        results = []
        for period_index, period in enumerate(selected):
            previous = comparable_financial_period(periods, period)
            previous_sequential = selected[period_index - 1] if period_index > 0 else None
            current_values = values(period)
            previous_values = values(previous)
            sequential_values = values(previous_sequential)
            quarter_periods = selected[max(0, period_index - 3) : period_index + 1]
            quarter_values = [values(item) for item in quarter_periods]

            def ttm(
                item_code: str,
                quarter_values=quarter_values,
                period_type=period.period_type,
            ) -> float | None:
                items = [item.get(item_code) for item in quarter_values]
                return (
                    sum(value for value in items if value is not None)
                    if period_type == "quarter"
                    and len(items) == 4
                    and all(value is not None for value in items)
                    else None
                )

            calculated = calculate_financial_metrics(
                FinancialInputs(
                    entity_type=_entity_type(security),
                    revenue=current_values.get("revenue"),
                    prior_revenue=previous_values.get("revenue"),
                    previous_period_revenue=sequential_values.get("revenue"),
                    ttm_revenue=ttm("revenue"),
                    net_income=current_values.get("net_income"),
                    net_income_attributable_to_parent=current_values.get(
                        "net_income_attributable_to_parent"
                    ),
                    prior_net_income=previous_values.get("net_income"),
                    previous_period_net_income=sequential_values.get("net_income"),
                    ttm_net_income=ttm("net_income"),
                    period_months=3 if period.period_type == "quarter" else 12,
                    total_assets=current_values.get("total_assets"),
                    prior_total_assets=previous_values.get("total_assets"),
                    total_equity=current_values.get("total_equity"),
                    prior_total_equity=previous_values.get("total_equity"),
                    total_debt=current_values.get("total_debt"),
                    prior_total_debt=previous_values.get("total_debt"),
                    cash_and_equivalents=current_values.get("cash_and_equivalents"),
                    prior_cash_and_equivalents=previous_values.get("cash_and_equivalents"),
                    current_assets=current_values.get("current_assets"),
                    inventory=current_values.get("inventory"),
                    current_liabilities=current_values.get("current_liabilities"),
                    operating_income=current_values.get("operating_income"),
                    profit_before_tax=current_values.get("profit_before_tax"),
                    tax_expense=current_values.get("tax_expense"),
                    gross_profit=current_values.get("gross_profit"),
                    interest_expense=current_values.get("interest_expense"),
                    operating_cash_flow=current_values.get("operating_cash_flow"),
                    ttm_operating_cash_flow=ttm("operating_cash_flow"),
                    capital_expenditure=current_values.get("capital_expenditure"),
                    ttm_capital_expenditure=ttm("capital_expenditure"),
                    shares_outstanding=current_values.get("shares_outstanding"),
                    diluted_shares_outstanding=current_values.get("weighted_average_shares"),
                    enterprise_value=current_values.get("enterprise_value"),
                    ebitda=current_values.get("ebitda"),
                )
            )
            metric_metadata = {
                code: metadata.model_copy(update={"as_of_date": period.period_end})
                for code, metadata in calculated.metric_metadata.items()
            }
            results.append(
                calculated.model_copy(
                    update={
                        "symbol": security.symbol,
                        "period_type": period.period_type,
                        "period_end": period.period_end,
                        "source_name": period.source_name,
                        "statement_scope": period.statement_scope,
                        "statement_status": period.statement_status,
                        "metric_metadata": metric_metadata,
                    }
                )
            )
        warnings = []
        if any(period.statement_status == "amended" for period in selected):
            warnings.append("Chuỗi có BCTC điều chỉnh; so sánh cần dùng phiên bản công bố mới nhất.")
        if len(periods) < 3:
            warnings.append("Chuỗi có ít hơn 3 kỳ; xu hướng dài hạn chưa đủ tin cậy.")
        if any(comparable_financial_period(periods, period) is None for period in selected):
            warnings.append(
                "Một số kỳ không có kỳ so sánh cùng loại của năm trước; tăng trưởng được để trống."
            )
        return FinancialTrendResponse(
            symbol=security.symbol,
            period_type=period_type,
            statement_scope=statement_scope,
            periods=results,
            warnings=warnings,
        )


class NewsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store(self, symbol: str, items: list[NewsItem]) -> list[NewsItem]:
        security = self.session.scalar(select(SecurityRecord).where(SecurityRecord.symbol == symbol.upper()))
        if security is None:
            return []
        stored: list[NewsItem] = []
        for item in items:
            url = str(item.url)
            existing = self.session.scalar(select(NewsArticleRecord).where(
                NewsArticleRecord.source_name == item.publisher, NewsArticleRecord.url == url
            ))
            digest = group_hash(item.title, item.published_at)
            values = {"security_id": security.id, "source_name": item.publisher, "source_url": item.source_url or url,
                "title": item.title, "normalized_title": normalize_vietnamese(item.title), "url": url,
                "published_at": item.published_at, "retrieved_at": item.retrieved_at or datetime.now(UTC),
                "relevance_score": Decimal(str(item.relevance_score)), "event_category": item.event_category,
                "event_summary": item.event_summary, "facts_json": json.dumps(item.facts, ensure_ascii=False),
                "implications_json": json.dumps(item.implications, ensure_ascii=False),
                "uncertainty_json": json.dumps(item.uncertainty, ensure_ascii=False), "evidence_json": json.dumps(item.evidence, ensure_ascii=False), "group_hash": digest}
            if existing is None:
                self.session.add(NewsArticleRecord(**values))
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
            event = self.session.scalar(select(NewsEventRecord).where(NewsEventRecord.group_hash == digest))
            if event is None:
                self.session.add(NewsEventRecord(security_id=security.id, group_hash=digest, event_category=item.event_category,
                    first_seen_at=item.retrieved_at or datetime.now(UTC), last_seen_at=item.retrieved_at or datetime.now(UTC),
                    article_count=1, summary=item.event_summary, evidence_json=json.dumps(item.evidence, ensure_ascii=False)))
            else:
                event.last_seen_at = item.retrieved_at or datetime.now(UTC)
                event.article_count += 1
            stored.append(item)
        self.session.commit()
        return stored

    def list(
        self,
        symbol: str,
        limit: int = 20,
        *,
        source: str | None = None,
        event_category: str | None = None,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
    ) -> list[NewsItem]:
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.upper())
        )
        if security is None:
            return []
        query = select(NewsArticleRecord).where(NewsArticleRecord.security_id == security.id)
        if source:
            query = query.where(NewsArticleRecord.source_name == source)
        if event_category:
            query = query.where(NewsArticleRecord.event_category == event_category)
        if published_from:
            query = query.where(NewsArticleRecord.published_at >= published_from)
        if published_to:
            query = query.where(NewsArticleRecord.published_at <= published_to)
        rows = self.session.scalars(
            query.order_by(NewsArticleRecord.published_at.desc()).limit(limit)
        ).all()
        return [NewsItem(title=r.title, publisher=r.source_name, published_at=r.published_at, url=r.url,
            related_symbols=[symbol.upper()], relevance_score=float(r.relevance_score), event_category=r.event_category,
            source_credibility="established_media", source_url=r.source_url, retrieved_at=r.retrieved_at,
            event_summary=r.event_summary, facts=json.loads(r.facts_json), implications=json.loads(r.implications_json),
            uncertainty=json.loads(r.uncertainty_json), evidence=json.loads(r.evidence_json)) for r in rows]

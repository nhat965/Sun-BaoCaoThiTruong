import csv
import json
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.analytics.fundamental import calculate_financial_metrics
from app.connectors.news import group_hash
from app.database import (
    AuditLogRecord,
    FinancialMetricRecord,
    FinancialPeriodRecord,
    FinancialStatementItemRecord,
    NewsArticleRecord,
    NewsEventRecord,
    PriceObservation,
    SecurityRecord,
    SourceHealthRecord,
)
from app.schemas import (
    FinancialInputs,
    FinancialMetricResult,
    FinancialStatementImportResult,
    FinancialTrendResponse,
    NewsItem,
    PriceSeries,
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
        rows = self.session.scalars(select(SecurityRecord).order_by(SecurityRecord.symbol)).all()
        matches = []
        for row in rows:
            if not include_inactive and row.listing_status != "active":
                continue
            aliases = json.loads(row.aliases_json)
            haystack = " ".join(
                [
                    row.symbol.lower(),
                    row.normalized_name,
                    *[normalize_vietnamese(a) for a in aliases],
                ]
            )
            if normalized in haystack:
                matches.append(security_schema(row))
            if len(matches) >= limit:
                break
        return matches

    def upsert(self, security: Security) -> tuple[Security, bool]:
        row = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == security.symbol.upper())
        )
        inserted = row is None
        if row is None:
            row = SecurityRecord(symbol=security.symbol.upper())
            self.session.add(row)
        row.name = security.name
        row.normalized_name = normalize_vietnamese(security.name)
        row.aliases_json = json.dumps(security.aliases, ensure_ascii=False)
        row.exchange = security.exchange.upper()
        row.industry = security.industry
        row.sector = security.sector
        row.listing_status = security.listing_status
        row.security_type = security.security_type
        row.provider_ids_json = json.dumps(security.provider_ids)
        row.source_name = security.source_name or "user-authorized-import"
        row.source_url = security.source_url
        row.last_updated = security.last_updated or datetime.now(UTC)
        row.currency = security.currency
        self.session.flush()
        return security_schema(row), inserted


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_series(self, series: PriceSeries) -> int:
        security_row = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == series.security.symbol)
        )
        if security_row is None:
            raise ValueError("Security must exist before storing prices")
        inserted = 0
        for bar in series.bars:
            values = {
                "security_id": security_row.id,
                "provider": series.provenance.source,
                "provider_symbol": series.provenance.provider_symbol,
                "market_timestamp": bar.timestamp,
                "ingested_at": series.provenance.retrieved_at,
                "interval": series.interval,
                "open": Decimal(str(bar.open)),
                "high": Decimal(str(bar.high)),
                "low": Decimal(str(bar.low)),
                "close": Decimal(str(bar.close)),
                "volume": bar.volume,
                "currency": series.security.currency,
                "adjusted": series.adjusted,
                "validation_status": series.provenance.validation_status,
                "adjustment_policy": series.provenance.adjustment_policy,
            }
            if self.session.bind and self.session.bind.dialect.name == "sqlite":
                statement = (
                    sqlite_insert(PriceObservation)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=["security_id", "provider", "market_timestamp", "interval"]
                    )
                )
                inserted += int((self.session.execute(statement).rowcount or 0) > 0)
            else:
                exists = self.session.scalar(
                    select(PriceObservation.id).where(
                        PriceObservation.security_id == security_row.id,
                        PriceObservation.provider == series.provenance.source,
                        PriceObservation.market_timestamp == bar.timestamp,
                        PriceObservation.interval == series.interval,
                    )
                )
                if exists is None:
                    self.session.add(PriceObservation(**values))
                    inserted += 1
        self.session.flush()
        return inserted


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
FINANCIAL_PERIOD_TYPES = {"quarter", "year", "ttm"}
FINANCIAL_STATEMENT_SCOPES = {"consolidated", "separate"}
FINANCIAL_STATEMENT_STATUSES = {"original", "amended"}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.strip())
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class FinancialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_csv(
        self, symbol: str, content: str, default_source: str
    ) -> FinancialStatementImportResult:
        security = self.session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        inserted_periods = updated_periods = inserted_items = updated_items = rejected = 0
        errors: list[str] = []
        seen_periods: set[tuple[datetime, str]] = set()
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
                period_type = (row.get("period_type") or "").strip().lower()
                statement_scope = (row.get("statement_scope") or "consolidated").strip().lower()
                statement_status = (row.get("statement_status") or "original").strip().lower()
                statement_type = (row.get("statement_type") or "").strip().lower()
                item_code = (row.get("item_code") or "").strip().lower()
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
                if not item_code or len(item_code) > 64:
                    raise ValueError("item_code is required and must be <= 64 characters")
                value = Decimal((row.get("value") or "").strip())
                fiscal_year = int((row.get("fiscal_year") or "").strip())
                quarter_text = (row.get("fiscal_quarter") or "").strip()
                fiscal_quarter = int(quarter_text) if quarter_text else None
                if fiscal_quarter is not None and fiscal_quarter not in {1, 2, 3, 4}:
                    raise ValueError("fiscal_quarter must be 1-4")
                period = self.session.scalar(
                    select(FinancialPeriodRecord).where(
                        FinancialPeriodRecord.security_id == security.id,
                        FinancialPeriodRecord.period_end == period_end,
                        FinancialPeriodRecord.period_type == period_type,
                        FinancialPeriodRecord.statement_scope == statement_scope,
                    )
                )
                source_name = (row.get("source_name") or default_source).strip()[:128]
                if period is None:
                    period = FinancialPeriodRecord(
                        security_id=security.id,
                        period_end=period_end,
                        period_type=period_type,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        reported_at=_parse_datetime(row.get("reported_at")),
                        source_name=source_name,
                        source_url=(row.get("source_url") or None),
                        verification_status=(
                            row.get("verification_status") or "unverified"
                        ).lower(),
                        statement_scope=statement_scope,
                        statement_status=statement_status,
                        unit=(row.get("unit") or "VND"),
                        currency=(row.get("currency") or "VND"),
                        updated_at=datetime.now(UTC),
                    )
                    self.session.add(period)
                    self.session.flush()
                    inserted_periods += 1
                else:
                    period.source_name = source_name
                    period.source_url = row.get("source_url") or period.source_url
                    period.verification_status = (
                        row.get("verification_status") or period.verification_status
                    ).lower()
                    period.statement_status = statement_status
                    period.updated_at = datetime.now(UTC)
                    period_key = (period_end, f"{period_type}:{statement_scope}")
                    if period_key not in seen_periods:
                        updated_periods += 1
                seen_periods.add((period_end, f"{period_type}:{statement_scope}"))
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
                            value=value,
                            unit=row.get("unit") or period.unit,
                            source_name=source_name,
                            source_url=row.get("source_url") or None,
                            verification_status=(
                                row.get("verification_status") or period.verification_status
                            ).lower(),
                            updated_at=datetime.now(UTC),
                        )
                    )
                    inserted_items += 1
                else:
                    item.value = value
                    item.source_name = source_name
                    item.source_url = row.get("source_url") or item.source_url
                    item.verification_status = (
                        row.get("verification_status") or item.verification_status
                    ).lower()
                    item.updated_at = datetime.now(UTC)
                    updated_items += 1
            except (ArithmeticError, TypeError, ValueError) as exc:
                rejected += 1
                errors.append(f"line {line_number}: {exc}")
        self.session.commit()
        return FinancialStatementImportResult(
            inserted_periods=inserted_periods,
            updated_periods=updated_periods,
            inserted_items=inserted_items,
            updated_items=updated_items,
            rejected=rejected,
            errors=errors[:100],
        )

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
                .order_by(FinancialPeriodRecord.period_end.desc())
            )
        )
        if not periods:
            raise LookupError(f"Chưa có dữ liệu BCTC cho {security.symbol}.")
        current = next(
            (period for period in periods if period.statement_scope == "consolidated"), periods[0]
        )
        previous = next(
            (
                period
                for period in periods
                if period.period_type == current.period_type
                and period.statement_scope == current.statement_scope
                and period.period_end < current.period_end
            ),
            None,
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
        with_price = self.session.scalar(
            select(PriceObservation.close)
            .join(SecurityRecord, PriceObservation.security_id == SecurityRecord.id)
            .where(SecurityRecord.id == security.id)
            .order_by(PriceObservation.market_timestamp.desc())
        )
        inputs = FinancialInputs(
            revenue=current_values.get("revenue"),
            prior_revenue=previous_values.get("revenue"),
            net_income=current_values.get("net_income"),
            prior_net_income=previous_values.get("net_income"),
            total_assets=current_values.get("total_assets"),
            prior_total_assets=previous_values.get("total_assets"),
            total_equity=current_values.get("total_equity"),
            prior_total_equity=previous_values.get("total_equity"),
            total_debt=current_values.get("total_debt"),
            current_assets=current_values.get("current_assets"),
            current_liabilities=current_values.get("current_liabilities"),
            operating_income=current_values.get("operating_income"),
            gross_profit=current_values.get("gross_profit"),
            interest_expense=current_values.get("interest_expense"),
            operating_cash_flow=current_values.get("operating_cash_flow"),
            capital_expenditure=current_values.get("capital_expenditure"),
            shares_outstanding=current_values.get("shares_outstanding"),
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
        return result.model_copy(
            update={
                "symbol": security.symbol,
                "period_type": current.period_type,
                "period_end": current.period_end,
                "source_name": current.source_name,
                "statement_scope": current.statement_scope,
                "statement_status": current.statement_status,
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
        for period in selected:
            index = periods.index(period)
            previous = periods[index - 1] if index > 0 else None
            current_values = values(period)
            previous_values = values(previous)
            calculated = calculate_financial_metrics(
                FinancialInputs(
                    revenue=current_values.get("revenue"),
                    prior_revenue=previous_values.get("revenue"),
                    net_income=current_values.get("net_income"),
                    prior_net_income=previous_values.get("net_income"),
                    total_assets=current_values.get("total_assets"),
                    prior_total_assets=previous_values.get("total_assets"),
                    total_equity=current_values.get("total_equity"),
                    prior_total_equity=previous_values.get("total_equity"),
                    total_debt=current_values.get("total_debt"),
                    current_assets=current_values.get("current_assets"),
                    current_liabilities=current_values.get("current_liabilities"),
                    operating_income=current_values.get("operating_income"),
                    gross_profit=current_values.get("gross_profit"),
                    interest_expense=current_values.get("interest_expense"),
                    operating_cash_flow=current_values.get("operating_cash_flow"),
                    capital_expenditure=current_values.get("capital_expenditure"),
                    shares_outstanding=current_values.get("shares_outstanding"),
                    enterprise_value=current_values.get("enterprise_value"),
                    ebitda=current_values.get("ebitda"),
                )
            )
            results.append(
                calculated.model_copy(
                    update={
                        "symbol": security.symbol,
                        "period_type": period.period_type,
                        "period_end": period.period_end,
                        "source_name": period.source_name,
                        "statement_scope": period.statement_scope,
                        "statement_status": period.statement_status,
                    }
                )
            )
        warnings = []
        if any(period.statement_status == "amended" for period in selected):
            warnings.append("Chuỗi có BCTC điều chỉnh; so sánh cần dùng phiên bản công bố mới nhất.")
        if len(periods) < 3:
            warnings.append("Chuỗi có ít hơn 3 kỳ; xu hướng dài hạn chưa đủ tin cậy.")
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

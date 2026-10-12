from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class SecurityRecord(Base):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    industry: Mapped[str | None] = mapped_column(String(128))
    sector: Mapped[str | None] = mapped_column(String(128))
    listing_status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    security_type: Mapped[str] = mapped_column(String(32), default="stock")
    provider_ids_json: Mapped[str] = mapped_column(Text, default="{}")
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(8), default="VND")

    prices: Mapped[list["PriceObservation"]] = relationship(back_populates="security")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint(
            "security_id", "provider", "market_timestamp", "interval", name="uq_price_point"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    provider_symbol: Mapped[str] = mapped_column(String(32))
    market_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval: Mapped[str] = mapped_column(String(16))
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    volume: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_status: Mapped[str] = mapped_column(String(24), default="valid")
    adjustment_policy: Mapped[str] = mapped_column(String(64), default="unadjusted")

    security: Mapped[SecurityRecord] = relationship(back_populates="prices")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24))
    formula_version: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(64))
    coverage: Mapped[str] = mapped_column(String(24))
    provenance_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"))
    format: Mapped[str] = mapped_column(String(16))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceHealthRecord(Base):
    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(String(512))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(24), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FinancialPeriodRecord(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("security_id", "period_end", "period_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_type: Mapped[str] = mapped_column(String(16), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified")
    unit: Mapped[str] = mapped_column(String(32), default="VND")
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FinancialStatementItemRecord(Base):
    __tablename__ = "financial_statement_items"
    __table_args__ = (UniqueConstraint("period_id", "statement_type", "item_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("financial_periods.id"), index=True)
    statement_type: Mapped[str] = mapped_column(String(24), index=True)
    item_code: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(28, 6))
    unit: Mapped[str] = mapped_column(String(32), default="VND")
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FinancialMetricRecord(Base):
    __tablename__ = "financial_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.id"), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 6), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="ratio")
    formula_version: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(128))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ValuationResultRecord(Base):
    __tablename__ = "valuation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    method: Mapped[str] = mapped_column(String(32))
    scenario: Mapped[str] = mapped_column(String(16))
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 6), nullable=True)
    assumptions_json: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CorporateActionRecord(Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint("security_id", "action_type", "effective_at", "source_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ratio: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NewsArticleRecord(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("source_name", "url", name="uq_news_source_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(128), index=True)
    source_url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(1024))
    normalized_title: Mapped[str] = mapped_column(String(1024), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    event_category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    event_summary: Mapped[str | None] = mapped_column(Text)
    facts_json: Mapped[str] = mapped_column(Text, default="[]")
    implications_json: Mapped[str] = mapped_column(Text, default="[]")
    uncertainty_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    group_hash: Mapped[str] = mapped_column(String(64), index=True)


class NewsEventRecord(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"), index=True)
    group_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_category: Mapped[str] = mapped_column(String(32), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    article_count: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("job_type", "symbol", "scheduled_for", name="uq_job_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobRunRecord(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(1024))
    result_json: Mapped[str] = mapped_column(Text, default="{}")


class WatchlistRecord(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("name", name="uq_watchlist_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    owner: Mapped[str] = mapped_column(String(128), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistItemRecord(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRuleRecord(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    rule_type: Mapped[str] = mapped_column(String(32))
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRecord(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("rule_id", "symbol", "dedupe_key", name="uq_alert_dedupe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    message: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")
engine_options: dict = {"connect_args": {"check_same_thread": False}} if is_sqlite else {}
if settings.database_url == "sqlite:///:memory:":
    engine_options["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    """Developer convenience; Alembic remains canonical for deployed databases."""
    Base.metadata.create_all(engine)

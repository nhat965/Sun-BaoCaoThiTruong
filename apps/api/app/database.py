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

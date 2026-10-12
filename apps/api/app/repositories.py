import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import PriceObservation, SecurityRecord
from app.schemas import PriceSeries, Security
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

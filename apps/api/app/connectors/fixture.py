from datetime import UTC, datetime, timedelta
from math import sin

from app.connectors.base import ConnectorError, DataCapability, MarketDataConnector
from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import PriceBar, PriceSeries, Provenance, Security


class FixtureConnector(MarketDataConnector):
    provider_id = "fixture"
    name = "Synthetic fixture (development only)"
    capabilities = frozenset({DataCapability.HISTORICAL_OHLCV})

    async def search(self, query: str) -> list[Security]:
        with SessionLocal() as session:
            return SecuritiesRepository(session).search(query)

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        with SessionLocal() as session:
            security = SecuritiesRepository(session).get(symbol, include_inactive=False)
        if security is None:
            raise ConnectorError(f"Mã {symbol.strip().upper()} không có trong securities master.")
        start = datetime(2025, 1, 2, tzinfo=UTC)
        bars = []
        for index in range(max(30, min(limit, 520))):
            close = 25000 + index * 22 + sin(index / 7) * 850
            bars.append(
                PriceBar(
                    timestamp=start + timedelta(days=index),
                    open=close - 90,
                    high=close + 220,
                    low=close - 260,
                    close=close,
                    volume=8_000_000 + (index % 17) * 180_000,
                )
            )
        return PriceSeries(
            security=security,
            interval="1d",
            adjusted=False,
            bars=bars,
            provenance=Provenance(
                source=self.name,
                provider_id=self.provider_id,
                provider_symbol=f"{security.symbol}.FIXTURE",
                retrieved_at=datetime.now(UTC),
                market_timestamp=bars[-1].timestamp,
                mode="fixture",
                delayed=True,
                validation_status="valid",
                adjustment_policy="synthetic-unadjusted",
                coverage="security",
                freshness="fixture",
                last_updated=datetime.now(UTC),
                notes="Dữ liệu tổng hợp xác định; không phải dữ liệu thị trường.",
            ),
        )

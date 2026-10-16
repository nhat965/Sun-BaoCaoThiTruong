from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum

from app.schemas import PriceSeries, Security


class ConnectorError(RuntimeError):
    """A stable boundary for external source failures."""


class UnsupportedCapabilityError(ConnectorError):
    """Raised when a provider does not declare a requested capability."""


class DataCapability(StrEnum):
    SECURITIES_METADATA = "securities_metadata"
    HISTORICAL_OHLCV = "historical_ohlcv"
    MARKET_INDICES = "market_indices"
    CORPORATE_ACTIONS = "corporate_actions"
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW_STATEMENT = "cash_flow_statement"


class MarketDataConnector(ABC):
    provider_id: str
    name: str
    capabilities: frozenset[DataCapability] = frozenset()

    def supports(self, capability: DataCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    async def search(self, query: str) -> list[Security]: ...

    @abstractmethod
    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries: ...

    async def prices_since(
        self, symbol: str, since: datetime | None, limit: int = 260
    ) -> PriceSeries:
        series = await self.prices(symbol, limit)
        if since is None:
            return series
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        return series.model_copy(
            update={"bars": [bar for bar in series.bars if bar.timestamp >= since]}
        )

    async def corporate_actions(self, symbol: str):
        raise UnsupportedCapabilityError(f"{self.name} does not provide corporate actions")

    async def financial_statements(self, symbol: str):
        raise UnsupportedCapabilityError(f"{self.name} does not provide financial statements")

    async def market_indices(self):
        raise UnsupportedCapabilityError(f"{self.name} does not provide market indices")

    async def securities_metadata(self):
        raise UnsupportedCapabilityError(f"{self.name} does not provide securities metadata")

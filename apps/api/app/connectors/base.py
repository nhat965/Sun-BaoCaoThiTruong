from abc import ABC, abstractmethod

from app.schemas import PriceSeries, Security


class ConnectorError(RuntimeError):
    """A stable boundary for external source failures."""


class UnsupportedCapabilityError(ConnectorError):
    """Raised when a provider does not declare a requested capability."""


class MarketDataConnector(ABC):
    name: str
    capabilities: frozenset[str] = frozenset({"search", "historical_prices"})

    @abstractmethod
    async def search(self, query: str) -> list[Security]: ...

    @abstractmethod
    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries: ...

    async def corporate_actions(self, symbol: str):
        raise UnsupportedCapabilityError(f"{self.name} does not provide corporate actions")

    async def financial_statements(self, symbol: str):
        raise UnsupportedCapabilityError(f"{self.name} does not provide financial statements")

    async def market_indices(self):
        raise UnsupportedCapabilityError(f"{self.name} does not provide market indices")

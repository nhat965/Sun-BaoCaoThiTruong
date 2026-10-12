from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.connectors.base import ConnectorError, MarketDataConnector
from app.connectors.fixture import FixtureConnector
from app.connectors.yahoo import YahooFinanceConnector
from app.schemas import PriceSeries


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: datetime | None = None


class ConnectorManager:
    failure_threshold = 3
    cooldown = timedelta(seconds=60)

    def __init__(self, settings: Settings) -> None:
        if settings.market_data_mode == "fixture":
            self.providers: list[MarketDataConnector] = [FixtureConnector()]
        else:
            configured = {"yahoo": YahooFinanceConnector(settings.request_timeout_seconds)}
            self.providers = [
                configured[name.strip()]
                for name in settings.market_provider_priority.split(",")
                if name.strip() in configured
            ]
        if not self.providers:
            raise ValueError("No market data providers are configured")
        self.circuits = {provider.name: CircuitState() for provider in self.providers}
        self.market = self.providers[0]

    def _available(self, provider: MarketDataConnector) -> bool:
        state = self.circuits[provider.name]
        if state.opened_at and datetime.now(UTC) - state.opened_at < self.cooldown:
            return False
        if state.opened_at:
            state.failures = 0
            state.opened_at = None
        return True

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        errors = []
        for provider in self.providers:
            if not self._available(provider):
                errors.append(f"{provider.name}: circuit open")
                continue
            try:
                series = await provider.prices(symbol, limit)
                self.circuits[provider.name].failures = 0
                return series
            except ConnectorError as exc:
                state = self.circuits[provider.name]
                state.failures += 1
                if state.failures >= self.failure_threshold:
                    state.opened_at = datetime.now(UTC)
                errors.append(f"{provider.name}: {exc}")
        raise ConnectorError("Tất cả nguồn giá cấu hình đều thất bại: " + "; ".join(errors))

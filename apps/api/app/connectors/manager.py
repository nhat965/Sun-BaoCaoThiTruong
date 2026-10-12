import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock

from app.config import Settings
from app.connectors.base import ConnectorError, MarketDataConnector
from app.connectors.fixture import FixtureConnector
from app.connectors.yahoo import YahooFinanceConnector
from app.database import SessionLocal
from app.repositories import SourceHealthRepository
from app.schemas import PriceSeries

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    failures: int = 0
    state: str = "closed"
    opened_at: datetime | None = None
    probe_in_flight: bool = False


@dataclass
class CircuitRegistry:
    states: dict[str, CircuitState] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def before_call(self, provider_name: str, cooldown: timedelta) -> bool:
        with self.lock:
            state = self.states.setdefault(provider_name, CircuitState())
            if state.state == "open":
                if state.opened_at is None or datetime.now(UTC) - state.opened_at < cooldown:
                    return False
                state.state = "half_open"
                state.probe_in_flight = False
            if state.state == "half_open":
                if state.probe_in_flight:
                    return False
                state.probe_in_flight = True
            return True

    def success(self, provider_name: str) -> CircuitState:
        with self.lock:
            state = self.states.setdefault(provider_name, CircuitState())
            state.failures = 0
            state.state = "closed"
            state.opened_at = None
            state.probe_in_flight = False
            return state

    def failure(self, provider_name: str, threshold: int) -> CircuitState:
        with self.lock:
            state = self.states.setdefault(provider_name, CircuitState())
            state.failures += 1
            state.probe_in_flight = False
            if state.failures >= threshold:
                state.state = "open"
                state.opened_at = datetime.now(UTC)
            return state

    def reset(self) -> None:
        with self.lock:
            self.states.clear()


@dataclass
class PriceCache:
    values: dict[tuple[str, str, int], tuple[datetime, PriceSeries]] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def get(self, key: tuple[str, str, int], *, allow_stale: bool = False) -> PriceSeries | None:
        with self.lock:
            item = self.values.get(key)
            if item is None:
                return None
            expires_at, series = item
            if allow_stale or expires_at > datetime.now(UTC):
                return series
            return None

    def put(self, key: tuple[str, str, int], series: PriceSeries, ttl_seconds: float) -> None:
        with self.lock:
            self.values[key] = (datetime.now(UTC) + timedelta(seconds=ttl_seconds), series)


DEFAULT_CIRCUIT_REGISTRY = CircuitRegistry()
DEFAULT_PRICE_CACHE = PriceCache()


class ConnectorManager:
    def __init__(
        self,
        settings: Settings,
        registry: CircuitRegistry | None = None,
        cache: PriceCache | None = None,
    ) -> None:
        self.failure_threshold = max(1, settings.circuit_failure_threshold)
        self.cooldown = timedelta(seconds=max(0.01, settings.circuit_cooldown_seconds))
        self.registry = registry or DEFAULT_CIRCUIT_REGISTRY
        self.cache = cache or DEFAULT_PRICE_CACHE
        self.cache_ttl_seconds = max(0, settings.market_cache_ttl_seconds)
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
        self.market = self.providers[0]

    def _record_health(self, provider: MarketDataConnector, *, success: bool, message: str) -> None:
        try:
            with SessionLocal() as session:
                SourceHealthRepository(session).record(
                    provider.name,
                    status="available" if success else "unavailable",
                    message=message,
                )
                session.commit()
        except Exception:  # pragma: no cover - health storage must not mask source errors
            logger.exception("Unable to persist provider health for %s", provider.name)

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        errors = []
        for provider in self.providers:
            cache_key = (provider.name, symbol.strip().upper(), limit)
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
            if not self.registry.before_call(provider.name, self.cooldown):
                errors.append(f"{provider.name}: circuit open")
                continue
            try:
                series = await provider.prices(symbol, limit)
                self.registry.success(provider.name)
                self._record_health(provider, success=True, message="request succeeded")
                self.cache.put(cache_key, series, self.cache_ttl_seconds)
                return series
            except ConnectorError as exc:
                state = self.registry.failure(provider.name, self.failure_threshold)
                self._record_health(provider, success=False, message=str(exc))
                logger.warning(
                    "Provider %s failed (%s/%s), circuit=%s",
                    provider.name,
                    state.failures,
                    self.failure_threshold,
                    state.state,
                )
                errors.append(f"{provider.name}: {exc}")
        for provider in self.providers:
            stale = self.cache.get((provider.name, symbol.strip().upper(), limit), allow_stale=True)
            if stale is not None:
                provenance = stale.provenance.model_copy(
                    update={
                        "notes": f"{stale.provenance.notes or ''}; served from stale cache after upstream failure",
                        "delayed": True,
                    }
                )
                return stale.model_copy(update={"provenance": provenance})
        raise ConnectorError("Tất cả nguồn giá cấu hình đều thất bại: " + "; ".join(errors))

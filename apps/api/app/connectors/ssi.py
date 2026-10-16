"""SSI FastConnect V3 adapter with an explicit, operator-supplied endpoint.

SSI documents the token exchange, but this repository does not invent a market
endpoint. The OHLC endpoint template is therefore required configuration. The
adapter is testable with an injected ``httpx.AsyncClient`` factory and never logs
the API key, secret, or returned token.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings
from app.connectors.base import ConnectorError, DataCapability, MarketDataConnector
from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import PriceBar, PriceSeries, Provenance, Security

try:  # The official SDK is optional at import time so CSV/fixture workflows stay independent.
    from ssi_fc_data import fc_md_client as _ssi_sdk_client
    from ssi_fc_data import model as _ssi_sdk_model
except ImportError:  # pragma: no cover - exercised in environments without the optional SDK
    _ssi_sdk_client = None
    _ssi_sdk_model = None


class SsiFastConnectConnector(MarketDataConnector):
    provider_id = "ssi_fastconnect"
    name = "SSI FastConnect API v3"
    capabilities = frozenset(
        {
            DataCapability.SECURITIES_METADATA,
            DataCapability.HISTORICAL_OHLCV,
            DataCapability.MARKET_INDICES,
        }
    )

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def search(self, query: str) -> list[Security]:
        with SessionLocal() as session:
            return SecuritiesRepository(session).search(query)

    def _resolve(self, symbol: str) -> Security:
        with SessionLocal() as session:
            security = SecuritiesRepository(session).get(symbol, include_inactive=False)
        if security is None:
            raise ConnectorError(f"Mã {symbol.strip().upper()} không có trong securities master.")
        return security

    async def _token(self, client: httpx.AsyncClient) -> str:
        if not self.settings.ssi_api_key or not self.settings.ssi_api_secret:
            raise ConnectorError("BLOCKED: SSI_API_KEY/SSI_API_SECRET are not configured.")
        try:
            response = await client.post(
                self.settings.ssi_auth_url,
                json={"apiKey": self.settings.ssi_api_key, "apiSecret": self.settings.ssi_api_secret},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError("SSI token request failed.") from exc
        token = None
        if isinstance(payload, dict):
            data = payload.get("data")
            candidates = [payload.get("accessToken"), payload.get("token")]
            if isinstance(data, dict):
                candidates.extend([data.get("accessToken"), data.get("token")])
            token = next((item for item in candidates if isinstance(item, str) and item), None)
        if not token:
            raise ConnectorError("SSI token response did not contain a usable access token.")
        return token

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("data", "result", "results", "rows"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
                if isinstance(value, dict):
                    nested = SsiFastConnectConnector._rows(value)
                    if nested:
                        return nested
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    @staticmethod
    def _row_value(row: dict[str, Any], *names: str) -> Any:
        normalized = {
            str(key).replace("_", "").lower(): value for key, value in row.items()
        }
        for name in names:
            value = normalized.get(name.replace("_", "").lower())
            if value is not None:
                return value
        return None

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            timestamp = datetime.fromisoformat(raw)
        except ValueError:
            try:
                timestamp = datetime.strptime(raw, "%d/%m/%Y")
            except ValueError:
                return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

    def _sdk_config(self) -> SimpleNamespace:
        return SimpleNamespace(
            auth_type="Bearer",
            consumerID=self.settings.ssi_api_key or "",
            consumerSecret=self.settings.ssi_api_secret or "",
            url=self.settings.ssi_data_base_url.rstrip("/") + "/",
            stream_url=self.settings.ssi_data_base_url.rstrip("/") + "/",
        )

    @classmethod
    def _sdk_bars(cls, payload: Any) -> list[PriceBar]:
        bars: list[PriceBar] = []
        for row in cls._rows(payload):
            timestamp = cls._timestamp(
                cls._row_value(row, "tradingDate", "trading_date", "timestamp", "date")
            )
            values = [
                cls._row_value(row, "openPrice", "open_price", "open"),
                cls._row_value(row, "highPrice", "high_price", "high"),
                cls._row_value(row, "lowPrice", "low_price", "low"),
                cls._row_value(row, "closePrice", "close_price", "close"),
            ]
            volume = cls._row_value(row, "volume", "totalVolume", "total_volume")
            if timestamp is None or any(value is None for value in values) or volume is None:
                continue
            try:
                bars.append(
                    PriceBar(
                        timestamp=timestamp,
                        open=float(values[0]),
                        high=float(values[1]),
                        low=float(values[2]),
                        close=float(values[3]),
                        volume=int(volume),
                        actual_trading_value=(
                            float(cls._row_value(row, "value", "tradingValue", "trading_value"))
                            if cls._row_value(row, "value", "tradingValue", "trading_value")
                            is not None
                            else None
                        ),
                    )
                )
            except (TypeError, ValueError):
                continue
        return bars

    async def _sdk_prices(self, symbol: str, limit: int) -> PriceSeries:
        if not self.settings.ssi_api_key or not self.settings.ssi_api_secret:
            raise ConnectorError(
                "BLOCKED: SSI_API_KEY/SSI_API_SECRET are not configured for the official SDK."
            )
        if _ssi_sdk_client is None or _ssi_sdk_model is None:
            raise ConnectorError(
                "BLOCKED: install the official ssi-fc-data package before enabling SSI."
            )
        security = self._resolve(symbol)
        provider_symbol = security.provider_ids.get(self.provider_id) or security.symbol
        page_size = min(max(limit, 1), 100)
        from_date = (date.today() - timedelta(days=365 * 5)).strftime("%d/%m/%Y")
        to_date = date.today().strftime("%d/%m/%Y")

        def fetch() -> list[PriceBar]:
            config = self._sdk_config()
            client = _ssi_sdk_client.MarketDataClient(config)
            collected: list[PriceBar] = []
            for page in range(1, 7):
                payload = client.daily_ohlc(
                    config,
                    _ssi_sdk_model.daily_ohlc(
                        provider_symbol,
                        from_date,
                        to_date,
                        page,
                        page_size,
                        True,
                    ),
                )
                page_bars = self._sdk_bars(payload)
                if not page_bars:
                    break
                collected.extend(page_bars)
                if len(page_bars) < page_size or len(collected) >= limit:
                    break
            return sorted(collected, key=lambda item: item.timestamp)[-max(1, min(limit, 520)) :]

        try:
            bars = await asyncio.to_thread(fetch)
        except ConnectorError:
            raise
        except Exception as exc:
            # Do not expose SDK response bodies or credentials in API errors/logs.
            raise ConnectorError("SSI official SDK DailyOhlc request failed.") from exc
        if not bars:
            raise ConnectorError("SSI official SDK DailyOhlc returned no valid observations.")
        retrieved_at = datetime.now(UTC)
        return PriceSeries(
            security=security,
            interval="1d",
            adjusted=False,
            bars=bars,
            provenance=Provenance(
                source=self.name,
                provider_id=self.provider_id,
                source_url=self.settings.ssi_data_base_url.rstrip("/") + "/api/v2/Market/DailyOhlc",
                provider_symbol=provider_symbol,
                retrieved_at=retrieved_at,
                market_timestamp=bars[-1].timestamp,
                mode="live",
                delayed=True,
                validation_status="partial",
                adjustment_policy="unadjusted; provider contract must define adjustments",
                coverage="security",
                freshness="daily/delayed",
                last_updated=retrieved_at,
                notes="Official SSI FastConnect Python SDK 2.x; entitlement must be verified.",
            ),
        )

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        template = self.settings.ssi_ohlc_endpoint_template
        if not template:
            return await self._sdk_prices(symbol, limit)
        security = self._resolve(symbol)
        provider_symbol = security.provider_ids.get(self.provider_id) or security.symbol
        try:
            url = template.format(symbol=provider_symbol)
        except (KeyError, ValueError) as exc:
            raise ConnectorError("SSI OHLC endpoint template must contain {symbol} only.") from exc
        try:
            async with self.client_factory(timeout=self.settings.request_timeout_seconds) as client:
                token = await self._token(client)
                response = await client.get(
                    url,
                    params={"symbol": provider_symbol, "page": 1, "size": limit},
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                payload = response.json()
        except ConnectorError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError("SSI OHLC request failed.") from exc
        bars: list[PriceBar] = []
        for row in self._rows(payload):
            raw_timestamp = self._row_value(row, "tradingDate", "trading_date", "timestamp", "date")
            timestamp = self._timestamp(raw_timestamp)
            if timestamp is None:
                continue
            try:
                values = [
                    self._row_value(row, "openPrice", "open_price", "open"),
                    self._row_value(row, "highPrice", "high_price", "high"),
                    self._row_value(row, "lowPrice", "low_price", "low"),
                    self._row_value(row, "closePrice", "close_price", "close"),
                ]
                volume = self._row_value(row, "volume", "totalVolume")
                if any(value is None for value in values) or volume is None:
                    continue
                bars.append(
                    PriceBar(
                        timestamp=timestamp,
                        open=float(values[0]),
                        high=float(values[1]),
                        low=float(values[2]),
                        close=float(values[3]),
                        volume=int(volume),
                        actual_trading_value=(
                            float(self._row_value(row, "value", "tradingValue"))
                            if self._row_value(row, "value", "tradingValue") is not None
                            else None
                        ),
                    )
                )
            except (TypeError, ValueError):
                continue
        if not bars:
            raise ConnectorError("SSI OHLC response contained no valid observations.")
        bars = sorted(bars, key=lambda item: item.timestamp)[-max(1, min(limit, 520)) :]
        retrieved_at = datetime.now(UTC)
        return PriceSeries(
            security=security,
            interval="1d",
            adjusted=False,
            bars=bars,
            provenance=Provenance(
                source=self.name,
                provider_id=self.provider_id,
                source_url=url,
                provider_symbol=provider_symbol,
                retrieved_at=retrieved_at,
                market_timestamp=bars[-1].timestamp,
                mode="live",
                delayed=True,
                validation_status="partial",
                adjustment_policy="unadjusted; provider contract must define adjustments",
                coverage="security",
                freshness="daily/delayed",
                last_updated=retrieved_at,
            ),
        )

    async def market_indices(self):
        if not self.settings.ssi_api_key or not self.settings.ssi_api_secret:
            raise ConnectorError(
                "BLOCKED: SSI_API_KEY/SSI_API_SECRET are not configured for the official SDK."
            )
        if _ssi_sdk_client is None or _ssi_sdk_model is None:
            raise ConnectorError(
                "BLOCKED: install the official ssi-fc-data package before enabling SSI indexes."
            )
        from_date = (date.today() - timedelta(days=365 * 5)).strftime("%d/%m/%Y")
        to_date = date.today().strftime("%d/%m/%Y")
        index_ids = ("VNINDEX", "VN30", "HNX", "UPCOM")

        def fetch() -> list[dict[str, Any]]:
            config = self._sdk_config()
            client = _ssi_sdk_client.MarketDataClient(config)
            result: list[dict[str, Any]] = []
            for index_id in index_ids:
                payload = client.daily_index(
                    config,
                    _ssi_sdk_model.daily_index(
                        "market-intelligence",
                        index_id,
                        from_date,
                        to_date,
                        1,
                        100,
                        "",
                        "",
                    ),
                )
                name, exchange = {
                    "VNINDEX": ("VN-Index", "HOSE"),
                    "VN30": ("VN30", "HOSE"),
                    "HNX": ("HNX-Index", "HNX"),
                    "UPCOM": ("UPCoM-Index", "UPCOM"),
                }[index_id]
                for row in self._rows(payload):
                    timestamp = self._timestamp(
                        self._row_value(row, "tradingDate", "indexDate", "date", "timestamp")
                    )
                    close = self._row_value(
                        row, "indexValue", "closeIndex", "close", "indexClose"
                    )
                    previous_close = self._row_value(
                        row, "previousClose", "prevClose", "previousIndex"
                    )
                    if timestamp is None or close is None:
                        continue
                    try:
                        result.append(
                            {
                                "symbol": index_id,
                                "name": name,
                                "exchange": exchange,
                                "market_session_date": timestamp.astimezone(
                                    ZoneInfo(self.settings.market_timezone)
                                ).date(),
                                "market_timestamp": timestamp,
                                "close": float(close),
                                "previous_close": (
                                    float(previous_close)
                                    if previous_close is not None
                                    else None
                                ),
                            }
                        )
                    except (TypeError, ValueError):
                        continue
            return result

        try:
            rows = await asyncio.to_thread(fetch)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("SSI official SDK DailyIndex request failed.") from exc
        if not rows:
            raise ConnectorError("SSI official SDK DailyIndex returned no valid observations.")
        retrieved_at = datetime.now(UTC)
        source_url = self.settings.ssi_data_base_url.rstrip("/") + "/api/v2/Market/DailyIndex"
        for row in rows:
            row.update(
                {
                    "provider": self.name,
                    "provider_id": self.provider_id,
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "last_updated": retrieved_at,
                    "data_mode": "live",
                    "validation_status": "partial",
                    "coverage": "index",
                    "freshness": "daily/delayed",
                    "adjustment_policy": "unadjusted; provider contract must define adjustments",
                }
            )
        return rows

    async def securities_metadata(self, markets: tuple[str, ...] = ("HOSE", "HNX", "UPCOM")):
        if not self.settings.ssi_api_key or not self.settings.ssi_api_secret:
            raise ConnectorError(
                "BLOCKED: SSI_API_KEY/SSI_API_SECRET are not configured for the official SDK."
            )
        if _ssi_sdk_client is None or _ssi_sdk_model is None:
            raise ConnectorError(
                "BLOCKED: install the official ssi-fc-data package before syncing securities."
            )

        def fetch() -> list[dict[str, Any]]:
            config = self._sdk_config()
            client = _ssi_sdk_client.MarketDataClient(config)
            collected: list[dict[str, Any]] = []
            for market in markets:
                for page in range(1, 21):
                    payload = client.securities(
                        config,
                        _ssi_sdk_model.securities(market, page, 100),
                    )
                    rows = self._rows(payload)
                    if not rows:
                        break
                    collected.extend(rows)
                    if len(rows) < 100:
                        break
            return collected

        try:
            rows = await asyncio.to_thread(fetch)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("SSI official SDK Securities request failed.") from exc
        retrieved_at = datetime.now(UTC)
        securities: list[Security] = []
        for row in rows:
            symbol = self._row_value(row, "symbol", "stockCode", "stock_code", "code")
            name = self._row_value(row, "stockName", "stock_name", "companyName", "name")
            exchange = self._row_value(row, "market", "exchange", "exchangeName")
            if not all(isinstance(value, str) and value.strip() for value in (symbol, name, exchange)):
                continue
            exchange_value = exchange.strip().upper()
            if exchange_value not in {"HOSE", "HNX", "UPCOM"}:
                continue
            securities.append(
                Security(
                    symbol=symbol.strip().upper(),
                    name=name.strip(),
                    exchange=exchange_value,
                    aliases=[],
                    listing_status="active",
                    security_type="stock",
                    provider_ids={self.provider_id: symbol.strip().upper()},
                    source_name=self.name,
                    source_url=self.settings.ssi_data_base_url.rstrip("/") + "/api/v2/Market/Securities",
                    last_updated=retrieved_at,
                )
            )
        if not securities:
            raise ConnectorError("SSI official SDK Securities returned no usable rows.")
        return securities

"""SSI FastConnect V3 adapter with an explicit, operator-supplied endpoint.

SSI documents the token exchange, but this repository does not invent a market
endpoint. The OHLC endpoint template is therefore required configuration. The
adapter is testable with an injected ``httpx.AsyncClient`` factory and never logs
the API key, secret, or returned token.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.connectors.base import ConnectorError, DataCapability, MarketDataConnector
from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import PriceBar, PriceSeries, Provenance, Security


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
        for name in names:
            if name in row and row[name] is not None:
                return row[name]
        return None

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        template = self.settings.ssi_ohlc_endpoint_template
        if not template:
            raise ConnectorError(
                "BLOCKED: configure SSI_OHLC_ENDPOINT_TEMPLATE from an approved SSI contract; "
                "the application will not guess an endpoint."
            )
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
            if not isinstance(raw_timestamp, str):
                continue
            try:
                if raw_timestamp.endswith("Z"):
                    raw_timestamp = f"{raw_timestamp[:-1]}+00:00"
                timestamp = datetime.fromisoformat(raw_timestamp)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
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
                        timestamp=timestamp.astimezone(UTC),
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
        raise ConnectorError(
            "BLOCKED: SSI index endpoint is not configured from an approved contract."
        )

"""Optional Vnstock v5 adapter.

Vnstock is a client library which routes requests to an upstream data source;
it is not itself a market-data entitlement.  The adapter is therefore lazy and
guarded: a missing package, missing registration, an upstream error, or an
empty response becomes a ``ConnectorError`` and never writes fabricated data.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.connectors.base import ConnectorError, DataCapability, MarketDataConnector
from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import PriceBar, PriceSeries, Provenance, Security

try:  # Keep CSV, fixture and SSI workflows installable without Vnstock.
    from vnstock import Market as _VnMarket
    from vnstock import Reference as _VnReference
except (ImportError, ModuleNotFoundError):  # pragma: no cover - optional environment
    _VnMarket = None
    _VnReference = None


class VnstockConnector(MarketDataConnector):
    provider_id = "vnstock"
    name = "Vnstock v5"
    capabilities = frozenset(
        {
            DataCapability.SECURITIES_METADATA,
            DataCapability.HISTORICAL_OHLCV,
            DataCapability.MARKET_INDICES,
        }
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _blocked_message() -> str:
        return (
            "BLOCKED: Vnstock v5 is not installed or could not be imported. "
            "Install the optional package from the official Vnstock package index, "
            "then run `vnstock register`/`vnstock status` with a permitted upstream source."
        )

    @classmethod
    def _ensure_available(cls) -> None:
        if _VnMarket is None or _VnReference is None:
            raise ConnectorError(cls._blocked_message())

    async def search(self, query: str) -> list[Security]:
        with SessionLocal() as session:
            return SecuritiesRepository(session).search(query)

    def _resolve(self, symbol: str) -> Security:
        with SessionLocal() as session:
            security = SecuritiesRepository(session).get(symbol, include_inactive=False)
        if security is None:
            raise ConnectorError(f"Mã {symbol.strip().upper()} không có trong securities master.")
        return security

    @staticmethod
    def _records(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if hasattr(value, "to_dict"):
            try:
                rows = value.to_dict("records")
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
            except (TypeError, ValueError):
                pass
        if isinstance(value, dict):
            return [value]
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return [row for row in value if isinstance(row, dict)]
        return []

    @staticmethod
    def _value(row: dict[str, Any], *names: str) -> Any:
        normalized = {
            str(key).replace("_", "").replace(" ", "").lower(): value
            for key, value in row.items()
        }
        for name in names:
            value = normalized.get(name.replace("_", "").replace(" ", "").lower())
            if value is not None:
                return value
        return None

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, date):
            timestamp = datetime.combine(value, datetime.min.time())
        else:
            raw = str(value or "").strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                timestamp = datetime.fromisoformat(raw)
            except ValueError:
                for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        timestamp = datetime.strptime(raw, pattern)
                        break
                    except ValueError:
                        continue
                else:
                    return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

    def _source_label(self, frame: Any) -> str:
        attrs = getattr(frame, "attrs", {}) or {}
        route = attrs.get("source") or attrs.get("route") or self.settings.vnstock_market_source
        return f"{self.name} ({route})" if route else self.name

    def _ohlcv(self, kind: str, symbol: str, limit: int) -> Any:
        self._ensure_available()
        source = self.settings.vnstock_market_source or None
        length = max(1, min(limit, 520))
        client = _VnMarket()
        try:
            instrument = getattr(client, kind)(symbol)
            return instrument.ohlcv(length=length, interval="1D", source=source)
        except TypeError:
            # A small compatibility shim for the module-style v5 surface.
            instrument = getattr(client, kind)
            return instrument.ohlcv(symbol=symbol, length=length, interval="1D", source=source)

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        self._ensure_available()
        security = self._resolve(symbol)
        provider_symbol = security.provider_ids.get(self.provider_id) or security.symbol
        try:
            frame = await asyncio.to_thread(self._ohlcv, "equity", provider_symbol, limit)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("Vnstock equity OHLCV request failed.") from exc
        bars: list[PriceBar] = []
        for row in self._records(frame):
            timestamp = self._timestamp(self._value(row, "time", "tradingDate", "date", "timestamp"))
            values = [
                self._value(row, "open"), self._value(row, "high"),
                self._value(row, "low"), self._value(row, "close"),
            ]
            volume = self._value(row, "volume", "vol")
            if timestamp is None or any(value is None for value in values) or volume is None:
                continue
            try:
                # Vnstock documents Vietnamese equity OHLCV prices in thousand
                # VND, while this application's PriceBar stores VND.
                scaled = [float(value) * 1000 for value in values]
                bars.append(
                    PriceBar(
                        timestamp=timestamp,
                        open=scaled[0], high=scaled[1], low=scaled[2], close=scaled[3],
                        volume=int(volume),
                        actual_trading_value=(
                            float(self._value(row, "value", "tradingValue", "trading_value"))
                            if self._value(row, "value", "tradingValue", "trading_value") is not None
                            else None
                        ),
                    )
                )
            except (TypeError, ValueError):
                continue
        bars = sorted({bar.timestamp: bar for bar in bars}.values(), key=lambda bar: bar.timestamp)
        bars = bars[-max(1, min(limit, 520)) :]
        if not bars:
            raise ConnectorError("Vnstock equity OHLCV returned no valid observations.")
        retrieved_at = datetime.now(UTC)
        return PriceSeries(
            security=security, interval="1d", adjusted=True, bars=bars,
            provenance=Provenance(
                source=self._source_label(frame), provider_id=self.provider_id,
                source_url="https://www.vnstocks.com/docs/vnstock/thi-truong-market",
                provider_symbol=provider_symbol, retrieved_at=retrieved_at,
                market_timestamp=bars[-1].timestamp, mode="live", delayed=True,
                validation_status="partial", adjustment_policy="provider-adjusted; corporate-action methodology not independently verified",
                coverage="security", freshness="daily/delayed", last_updated=retrieved_at,
                notes="Vnstock client response; upstream source entitlement and rights require operator verification.",
            ),
        )

    async def prices_since(
        self, symbol: str, since: datetime | None, limit: int = 260
    ) -> PriceSeries:
        """Fetch a bounded recent window for incremental sync.

        Vnstock's documented daily surface accepts a length, not a cursor. A
        daily replay therefore only requests a recent reconciliation window
        instead of downloading the complete 520-session history each time.
        The persisted cursor still determines which bars are written.
        """
        if since is None:
            return await self.prices(symbol, limit)
        window = min(max(limit, 30), 60)
        series = await self.prices(symbol, window)
        cursor = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
        bars = [bar for bar in series.bars if bar.timestamp > cursor]
        note = "incremental bounded reconciliation window (up to 60 sessions)"
        provenance = series.provenance.model_copy(
            update={"notes": f"{series.provenance.notes}; {note}"}
        )
        return series.model_copy(update={"bars": bars, "provenance": provenance})

    async def market_indices(self) -> list[dict[str, Any]]:
        self._ensure_available()
        index_ids = (
            ("VNINDEX", "VN-Index", "HOSE"),
            ("VN30", "VN30", "HOSE"),
            ("HNXINDEX", "HNX-Index", "HNX"),
            ("UPCOMINDEX", "UPCoM-Index", "UPCOM"),
        )

        async def fetch_one(index_id: str, name: str, exchange: str) -> list[dict[str, Any]]:
            try:
                frame = await asyncio.to_thread(self._ohlcv, "index", index_id, 520)
            except Exception as exc:
                raise ConnectorError(f"Vnstock index {index_id} request failed.") from exc
            rows: list[dict[str, Any]] = []
            retrieved_at = datetime.now(UTC)
            for row in self._records(frame):
                timestamp = self._timestamp(self._value(row, "time", "date", "timestamp", "tradingDate"))
                close = self._value(row, "close", "indexValue", "indexClose")
                if timestamp is None or close is None:
                    continue
                try:
                    rows.append({
                        "symbol": index_id, "name": name, "exchange": exchange,
                        "market_session_date": timestamp.astimezone(ZoneInfo(self.settings.market_timezone)).date(),
                        "market_timestamp": timestamp, "close": float(close),
                        "previous_close": (
                            float(self._value(row, "previousClose", "prevClose"))
                            if self._value(row, "previousClose", "prevClose") is not None else None
                        ),
                        "provider": self._source_label(frame), "provider_id": self.provider_id,
                        "source_url": "https://www.vnstocks.com/docs/vnstock/thi-truong-market",
                        "retrieved_at": retrieved_at, "last_updated": retrieved_at,
                        "data_mode": "live", "validation_status": "partial", "coverage": "index",
                        "freshness": "daily/delayed", "adjustment_policy": "provider-adjusted; methodology not independently verified",
                    })
                except (TypeError, ValueError):
                    continue
            return rows

        groups = await asyncio.gather(*(fetch_one(*item) for item in index_ids))
        rows = [row for group in groups for row in group]
        if not rows:
            raise ConnectorError("Vnstock index endpoints returned no valid observations.")
        return rows

    async def securities_metadata(self, markets: tuple[str, ...] = ("HOSE", "HNX", "UPCOM")) -> list[Security]:
        self._ensure_available()

        def fetch() -> Any:
            reference = _VnReference()
            source = self.settings.vnstock_reference_source or None
            method = reference.equity.list_by_exchange
            try:
                return method(source=source)
            except TypeError:
                return method()

        try:
            frame = await asyncio.to_thread(fetch)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("Vnstock equity reference request failed.") from exc
        allowed = {market.upper() for market in markets}
        retrieved_at = datetime.now(UTC)
        securities: list[Security] = []
        for row in self._records(frame):
            symbol = self._value(row, "symbol", "code", "ticker")
            name = self._value(row, "organ_name", "org_name", "organization", "name")
            exchange = self._value(row, "exchange", "market")
            if not all(isinstance(value, str) and value.strip() for value in (symbol, name, exchange)):
                continue
            exchange_value = exchange.strip().upper()
            if exchange_value not in allowed:
                continue
            industry = self._value(row, "icb_name", "industry", "sector")
            securities.append(Security(
                symbol=symbol.strip().upper(), name=name.strip(), exchange=exchange_value,
                industry=str(industry).strip() if industry else None,
                provider_ids={self.provider_id: symbol.strip().upper()}, source_name=self._source_label(frame),
                source_url="https://www.vnstocks.com/docs/vnstock/tham-chieu-reference",
                last_updated=retrieved_at,
            ))
        if not securities:
            raise ConnectorError("Vnstock equity reference returned no usable rows.")
        return securities

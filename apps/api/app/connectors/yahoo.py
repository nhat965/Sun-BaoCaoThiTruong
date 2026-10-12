from datetime import UTC, datetime

import httpx

from app.connectors.base import ConnectorError, MarketDataConnector
from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import PriceBar, PriceSeries, Provenance, Security


class YahooFinanceConnector(MarketDataConnector):
    name = "Yahoo Finance chart"

    def __init__(self, timeout: float = 12) -> None:
        self.timeout = timeout

    async def search(self, query: str) -> list[Security]:
        with SessionLocal() as session:
            return SecuritiesRepository(session).search(query)

    def _resolve(self, symbol: str) -> Security:
        with SessionLocal() as session:
            security = SecuritiesRepository(session).get(symbol, include_inactive=False)
        if security is None:
            raise ConnectorError(f"Mã {symbol.strip().upper()} không có trong securities master.")
        return security

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        security = self._resolve(symbol)
        provider_symbol = security.provider_ids.get("yahoo") or f"{security.symbol}.VN"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}"
        params = {"range": "2y", "interval": "1d", "events": "div,splits"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    url, params=params, headers={"User-Agent": "market-intelligence-mvp/0.2"}
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"Không thể truy cập nguồn giá: {exc}") from exc

        try:
            result = payload["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            timestamps = result["timestamp"]
            bars = []
            for idx, unix_time in enumerate(timestamps):
                values = [quote[key][idx] for key in ("open", "high", "low", "close", "volume")]
                if any(value is None for value in values):
                    continue
                bars.append(
                    PriceBar(
                        timestamp=datetime.fromtimestamp(unix_time, tz=UTC),
                        open=values[0],
                        high=values[1],
                        low=values[2],
                        close=values[3],
                        volume=int(values[4]),
                    )
                )
        except (KeyError, IndexError, TypeError) as exc:
            raise ConnectorError("Phản hồi nguồn giá không đúng cấu trúc mong đợi.") from exc
        if not bars:
            raise ConnectorError("Nguồn giá không trả về quan sát hợp lệ.")
        bars = bars[-max(30, min(limit, 520)) :]
        meta = result.get("meta", {})
        return PriceSeries(
            security=security,
            interval="1d",
            adjusted=False,
            bars=bars,
            provenance=Provenance(
                source=self.name,
                source_url=str(response.url),
                provider_symbol=provider_symbol,
                retrieved_at=datetime.now(UTC),
                market_timestamp=bars[-1].timestamp,
                mode="live",
                delayed=True,
                validation_status="partial",
                adjustment_policy="unadjusted; corporate actions not independently verified",
                notes=(
                    f"currency={meta.get('currency', 'VND')}; "
                    f"exchangeTimezone={meta.get('exchangeTimezoneName', 'unknown')}"
                ),
            ),
        )

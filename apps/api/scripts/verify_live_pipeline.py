"""Run a reproducible real-price ingestion and idempotency check.

The caller must explicitly set MARKET_DATA_MODE=live and DATABASE_URL. The script
never enables fixture fallback, and its JSON output preserves source/timestamps.
"""

import argparse
import asyncio
import json

from sqlalchemy import func, select

from app.config import Settings
from app.data_pipeline import DataSyncService
from app.database import PriceObservation, SecurityRecord, SessionLocal, init_db
from app.registry import seed_registry_if_empty


def observation_count(symbol: str, provider: str) -> int:
    with SessionLocal() as session:
        security_id = session.scalar(
            select(SecurityRecord.id).where(SecurityRecord.symbol == symbol)
        )
        return int(
            session.scalar(
                select(func.count(PriceObservation.id)).where(
                    PriceObservation.security_id == security_id,
                    PriceObservation.provider == provider,
                )
            )
            or 0
        )


async def verify(symbols: list[str], limit: int) -> list[dict[str, object]]:
    settings = Settings()
    if settings.market_data_mode != "live":
        raise RuntimeError("MARKET_DATA_MODE must be live; fixture verification is rejected.")
    init_db()
    seed_registry_if_empty()
    service = DataSyncService(settings)
    output = []
    for raw_symbol in symbols:
        symbol = raw_symbol.strip().upper()
        first = await service.sync_prices(symbol, provider_id="yahoo", limit=limit)
        count_after_first = observation_count(symbol, "Yahoo Finance chart")
        second = await service.sync_prices(symbol, provider_id="yahoo", limit=limit)
        count_after_second = observation_count(symbol, "Yahoo Finance chart")
        output.append(
            {
                "symbol": symbol,
                "first_sync": first.model_dump(mode="json"),
                "second_sync": second.model_dump(mode="json"),
                "rows_after_first": count_after_first,
                "rows_after_second": count_after_second,
                "duplicate_rows_created": count_after_second != count_after_first,
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+", help="Registry symbols, for example HPG FPT")
    parser.add_argument("--limit", type=int, default=120)
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(verify(arguments.symbols, arguments.limit)), indent=2))


if __name__ == "__main__":
    main()

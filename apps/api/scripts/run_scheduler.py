"""Run the production scheduler outside the FastAPI process.

Examples:
  python scripts/run_scheduler.py --once
  SCHEDULER_ENABLED=true python scripts/run_scheduler.py
"""
import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.scheduler import ProductionScheduler


async def main(once: bool, initialize_schema: bool) -> None:
    settings = get_settings()
    if initialize_schema:
        from app.database import init_db

        init_db()
    scheduler = ProductionScheduler(settings)
    if once:
        print(await scheduler.run_cycle())
        return
    if not settings.scheduler_enabled:
        raise SystemExit("SCHEDULER_ENABLED=false; use --once for an explicit operator run")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    await scheduler.run_forever(stop)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="enqueue and process one configured slot")
    parser.add_argument("--init-db", action="store_true", help="developer-only create_all; production uses Alembic before worker start")
    args = parser.parse_args()
    asyncio.run(main(args.once, args.init_db))

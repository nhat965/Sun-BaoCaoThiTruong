"""Rate-limited, resumable Vnstock OHLCV backfill.

This command deliberately calls the explicit ``vnstock`` provider.  It never
falls back to Yahoo, fixture data, or an undocumented endpoint.  The
checkpoint is operational state only and contains no credentials.

Examples::

    python scripts/vnstock_backfill.py --max-symbols 5 --batch-size 5
    python scripts/vnstock_backfill.py --max-symbols 20 --batch-size 20
    python scripts/vnstock_backfill.py --all --batch-size 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import Settings
from app.connectors.base import ConnectorError
from app.data_pipeline import DataSyncService
from app.database import SecurityRecord, SessionLocal

LOGGER = logging.getLogger("vnstock_backfill")
_BLOCK_PATTERNS = re.compile(r"(?:429|403|rate.?limit|quota|forbidden|permission|entitlement)", re.IGNORECASE)
_UNSUPPORTED_PATTERNS = re.compile(r"(?:unsupported|not supported|no valid observations|no data|empty response)", re.IGNORECASE)


def _default_checkpoint() -> Path:
    return Path(".runtime") / "vnstock_backfill_checkpoint.json"


def _load_checkpoint(path: Path, provider: str, limit: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "provider": provider,
            "limit": limit,
            "updated_at": None,
            "symbols": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read checkpoint {path}: {exc}") from exc
    if payload.get("provider") != provider:
        raise RuntimeError("Checkpoint provider does not match the explicit provider request.")
    return payload


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(UTC).isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _symbols(limit: int | None, explicit: str | None) -> list[str]:
    if explicit:
        requested = [value.strip().upper() for value in explicit.split(",") if value.strip()]
        with SessionLocal() as session:
            known = set(
                session.scalars(
                    select(SecurityRecord.symbol).where(SecurityRecord.symbol.in_(requested))
                ).all()
                )
        unknown = sorted(set(requested) - known)
        if unknown:
            raise RuntimeError(f"Symbols are not in the securities master: {', '.join(unknown)}")
        return list(dict.fromkeys(requested))
    with SessionLocal() as session:
        query = select(SecurityRecord.symbol).where(SecurityRecord.listing_status == "active").order_by(SecurityRecord.symbol)
        if limit is not None:
            query = query.limit(limit)
        return list(session.scalars(query).all())


def _classify_error(message: str) -> str:
    if _BLOCK_PATTERNS.search(message):
        return "provider_blocked"
    if _UNSUPPORTED_PATTERNS.search(message):
        return "unsupported"
    return "failed"


def _should_skip(entry: dict[str, Any], requested_limit: int) -> bool:
    return entry.get("status") == "SUCCESS" and int(entry.get("limit", 0)) >= requested_limit


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings()
    service = DataSyncService(settings)
    checkpoint_path = Path(args.checkpoint)
    checkpoint = _load_checkpoint(checkpoint_path, "vnstock", args.limit)
    symbols = _symbols(None if args.all else args.max_symbols, args.symbols)
    checkpoint["limit"] = args.limit
    checkpoint["selection"] = {
        "requested": len(symbols),
        "all": bool(args.all),
        "batch_size": args.batch_size,
    }
    if args.dry_run:
        return {"status": "DRY_RUN", "symbols": symbols, "checkpoint": str(checkpoint_path)}

    counters = {"success": 0, "skipped": 0, "failed": 0, "unsupported": 0, "provider_blocked": 0}
    started = datetime.now(UTC)
    for index in range(0, len(symbols), args.batch_size):
        batch = symbols[index : index + args.batch_size]
        LOGGER.info("Starting batch %s-%s (%s symbols)", index + 1, index + len(batch), len(batch))
        for symbol in batch:
            entry = checkpoint["symbols"].get(symbol, {})
            if _should_skip(entry, args.limit) and not args.force:
                counters["skipped"] += 1
                continue
            completed = False
            for attempt in range(1, args.retries + 2):
                try:
                    run = await service.sync_prices(
                        symbol,
                        provider_id="vnstock",
                        requested_mode="incremental" if entry.get("status") == "SUCCESS" else "initial",
                        limit=args.limit,
                    )
                except (ConnectorError, ValueError) as exc:
                    message = str(exc)[:500]
                    category = _classify_error(message)
                    if attempt <= args.retries and category not in {"provider_blocked", "unsupported"}:
                        delay = args.backoff_seconds * (2 ** (attempt - 1))
                        LOGGER.warning("%s failed (attempt %s); retrying in %.1fs", symbol, attempt, delay)
                        await asyncio.sleep(delay)
                        continue
                    entry.update({
                        "status": category.upper(),
                        "limit": args.limit,
                        "attempts": attempt,
                        "error": message,
                        "updated_at": datetime.now(UTC).isoformat(),
                    })
                    checkpoint["symbols"][symbol] = entry
                    _save_checkpoint(checkpoint_path, checkpoint)
                    counters[category] += 1
                    if category == "provider_blocked":
                        checkpoint["status"] = "PAUSED_PROVIDER_LIMIT"
                        _save_checkpoint(checkpoint_path, checkpoint)
                        return _summary(counters, started, checkpoint_path, symbols, checkpoint)
                    break
                else:
                    details = run.details or {}
                    entry.update({
                        "status": run.status,
                        "limit": args.limit,
                        "run_id": run.id,
                        "inserted_count": run.inserted_count,
                        "updated_count": run.updated_count,
                        "skipped_count": run.skipped_count,
                        "error_count": run.error_count,
                        "cursor_to": run.cursor_to.isoformat() if run.cursor_to else None,
                        "source_name": details.get("source_name"),
                        "source_mode": details.get("source_mode"),
                        "retrieved_at": details.get("retrieved_at"),
                        "updated_at": datetime.now(UTC).isoformat(),
                    })
                    checkpoint["symbols"][symbol] = entry
                    _save_checkpoint(checkpoint_path, checkpoint)
                    counters["success"] += 1
                    completed = True
                    break
            if not completed and symbol not in checkpoint["symbols"]:
                counters["failed"] += 1
            await asyncio.sleep(max(0.0, args.pause_seconds))
    checkpoint["status"] = "COMPLETE"
    _save_checkpoint(checkpoint_path, checkpoint)
    return _summary(counters, started, checkpoint_path, symbols, checkpoint)


def _summary(
    counters: dict[str, int],
    started: datetime,
    checkpoint_path: Path,
    symbols: list[str],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": checkpoint.get("status", "RUNNING"),
        "provider": "vnstock",
        "requested_symbols": len(symbols),
        "counters": counters,
        "elapsed_seconds": round((datetime.now(UTC) - started).total_seconds(), 2),
        "checkpoint": str(checkpoint_path),
        "source_modes": sorted({
            str(entry.get("source_mode"))
            for entry in checkpoint.get("symbols", {}).values()
            if entry.get("source_mode")
        }),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=False)
    scope.add_argument("--max-symbols", type=int, default=5, help="Select the first N active symbols (safe default: 5)")
    scope.add_argument("--all", action="store_true", help="Select the complete active universe")
    parser.add_argument("--symbols", help="Comma-separated symbols already in the securities master")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--limit", type=int, default=520, help="Maximum daily bars requested per symbol")
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--backoff-seconds", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--checkpoint", default=str(_default_checkpoint()))
    parser.add_argument("--force", action="store_true", help="Re-request symbols marked SUCCESS")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.batch_size < 1 or args.limit < 30 or args.limit > 520:
        raise SystemExit("--batch-size must be positive and --limit must be between 30 and 520")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

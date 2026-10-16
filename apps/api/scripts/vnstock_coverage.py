"""Report persisted Vnstock OHLCV coverage and quality without contacting providers.

The report deliberately separates the securities master from provider attempts.  A
symbol with no bars is not labelled ``unsupported`` unless the provider recorded an
explicit unsupported/no-data response; symbols with no attempt remain
``not_backfilled``.  This prevents a partial backfill from being presented as a
full-market entitlement result.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.database import (
    DataSyncErrorRecord,
    DataSyncRunRecord,
    FinancialPeriodRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
)

UNSUPPORTED_TERMS = (
    "unsupported",
    "not supported",
    "no data",
    "no valid",
    "không hỗ trợ",
    "không có dữ liệu",
)


def _is_unsupported(message: str | None, error_code: str | None = None) -> bool:
    text = f"{error_code or ''} {message or ''}".lower()
    return any(term in text for term in UNSUPPORTED_TERMS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        help="Optional JSON output path (for an auditable before/after snapshot).",
    )
    args = parser.parse_args()
    with SessionLocal() as session:
        active = list(
            session.scalars(
                select(SecurityRecord).where(SecurityRecord.listing_status == "active")
            ).all()
        )
        rows = list(
            session.scalars(
                select(PriceObservation)
                .where(PriceObservation.provider_id == "vnstock")
                .order_by(PriceObservation.security_id, PriceObservation.market_timestamp)
            ).all()
        )
        runs = list(
            session.scalars(
                select(DataSyncRunRecord)
                .where(
                    DataSyncRunRecord.provider == "vnstock",
                    DataSyncRunRecord.capability == "historical_ohlcv",
                    DataSyncRunRecord.symbol.is_not(None),
                )
                .order_by(DataSyncRunRecord.finished_at.desc())
            ).all()
        )
        run_ids = [run.id for run in runs]
        errors = (
            list(
                session.scalars(
                    select(DataSyncErrorRecord).where(
                        DataSyncErrorRecord.run_id.in_(run_ids)
                    )
                ).all()
            )
            if run_ids
            else []
        )
        financial_periods = list(
            session.scalars(select(FinancialPeriodRecord)).all()
        )
        financial_security_ids = {
            period.security_id for period in financial_periods
        }
        duplicate_groups = session.execute(
            select(
                PriceObservation.security_id,
                PriceObservation.market_session_date,
                PriceObservation.interval,
                PriceObservation.adjusted,
                func.count(PriceObservation.id),
            )
            .where(PriceObservation.provider_id == "vnstock")
            .group_by(
                PriceObservation.security_id,
                PriceObservation.market_session_date,
                PriceObservation.interval,
                PriceObservation.adjusted,
            )
            .having(func.count(PriceObservation.id) > 1)
        ).all()

    per_symbol: dict[int, list[PriceObservation]] = defaultdict(list)
    for row in rows:
        per_symbol[row.security_id].append(row)
    symbol_names = {security.id: security.symbol for security in active}
    invalid_ohlc = 0
    negative_volume = 0
    zero_volume = 0
    stale_or_partial = 0
    source_modes = Counter()
    adjusted = Counter()
    flagged_gaps = 0
    for row in rows:
        if row.high < max(row.open, row.close, row.low) or row.low > min(row.open, row.close, row.high):
            invalid_ohlc += 1
        if row.volume < 0:
            negative_volume += 1
        if row.volume == 0:
            zero_volume += 1
        if row.validation_status != "valid":
            stale_or_partial += 1
        source_modes[row.source_mode] += 1
        adjusted[str(bool(row.adjusted))] += 1
        try:
            flags = json.loads(row.quality_flags_json or "[]")
        except ValueError:
            flags = []
        if "calendar_gap_over_4_days" in flags:
            flagged_gaps += 1

    counts = {symbol_names.get(key, str(key)): len(value) for key, value in per_symbol.items()}
    coverage = {
        str(threshold): sum(1 for count in counts.values() if count >= threshold)
        for threshold in (20, 50, 200)
    }
    missing = sorted(security.symbol for security in active if security.id not in per_symbol)
    active_symbols = {security.symbol for security in active}
    # The last run is the authoritative attempt state for a symbol.  Failed and
    # blocked runs are retained so operators can distinguish a provider response
    # from work that has not been scheduled yet.
    latest_run_by_symbol: dict[str, DataSyncRunRecord] = {}
    for run in runs:
        if run.symbol and run.symbol not in latest_run_by_symbol:
            latest_run_by_symbol[run.symbol] = run
    error_by_run = {error.run_id: error for error in errors}
    data_symbols = {
        symbol_names[security_id]
        for security_id in per_symbol
        if security_id in symbol_names
    }
    attempted = sorted(active_symbols.intersection(set(latest_run_by_symbol) | data_symbols))
    unsupported = sorted(
        symbol
        for symbol, run in latest_run_by_symbol.items()
        if symbol in active_symbols
        and (
            run.status in {"BLOCKED", "FAILED"}
            and _is_unsupported(
                run.error_message,
                error_by_run.get(run.id).error_code if error_by_run.get(run.id) else None,
            )
        )
    )
    failed = sorted(
        symbol
        for symbol, run in latest_run_by_symbol.items()
        if symbol in active_symbols
        and run.status in {"BLOCKED", "FAILED"}
        and symbol not in unsupported
    )
    not_backfilled = sorted(active_symbols.difference(attempted))
    exchange_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    security_type_counts: dict[str, int] = Counter()
    listing_status_counts: dict[str, int] = Counter()
    for security in active:
        exchange_counts[security.exchange or "UNKNOWN"][security.security_type or "UNKNOWN"] += 1
        security_type_counts[security.security_type or "UNKNOWN"] += 1
        listing_status_counts[security.listing_status or "UNKNOWN"] += 1
    financial_symbols = sorted(
        security.symbol
        for security in active
        if security.id in financial_security_ids
    )
    payload = {
        "report": "vnstock_coverage_recovery_audit",
        "provider": "vnstock",
        "generated_at": datetime.now(UTC).isoformat(),
        "active_universe": len(active),
        "active_universe_by_exchange_and_security_type": {
            exchange: dict(types) for exchange, types in sorted(exchange_counts.items())
        },
        "active_universe_by_security_type": dict(sorted(security_type_counts.items())),
        "active_universe_by_listing_status": dict(sorted(listing_status_counts.items())),
        "symbols_with_ohlcv": len(counts),
        "symbols_missing_ohlcv": len(missing),
        "missing_sample": missing[:50],
        "provider_attempts": {
            "attempted_symbols": len(attempted),
            "symbols_with_ohlcv": len(data_symbols),
            "not_backfilled_symbols": len(not_backfilled),
            "not_backfilled_sample": not_backfilled[:50],
            "unsupported_symbols": len(unsupported),
            "unsupported_sample": unsupported[:50],
            "failed_or_blocked_symbols": len(failed),
            "failed_or_blocked_sample": failed[:50],
            "latest_status_counts": dict(Counter(run.status for run in latest_run_by_symbol.values())),
        },
        "financial_statement_coverage": {
            "symbols_with_periods": len(financial_symbols),
            "symbols": financial_symbols[:100],
            "period_records": len(financial_periods),
        },
        "ohlcv_records": len(rows),
        "coverage_symbols_by_min_sessions": coverage,
        "min_sessions": min(counts.values()) if counts else 0,
        "max_sessions": max(counts.values()) if counts else 0,
        "source_modes": dict(source_modes),
        "adjusted": dict(adjusted),
        "quality": {
            "invalid_ohlc": invalid_ohlc,
            "negative_volume": negative_volume,
            "zero_volume": zero_volume,
            "partial_or_unvalidated": stale_or_partial,
            "flagged_calendar_gaps": flagged_gaps,
            "duplicate_groups": len(duplicate_groups),
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()

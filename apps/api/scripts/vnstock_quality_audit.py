"""Audit persisted Vnstock prices for anomalies and calendar gaps.

This is a read-only audit.  It never rewrites prices or promotes a warning to a
verified corporate-action adjustment.  Without an authorised exchange calendar,
calendar gaps are reported as ``UNCONFIRMED`` rather than missing sessions.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise

from sqlalchemy import select

from app.database import CorporateActionRecord, PriceObservation, SecurityRecord, SessionLocal


def _as_float(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--threshold", type=float, default=0.20)
    args = parser.parse_args()

    with SessionLocal() as session:
        securities = {
            row.id: row
            for row in session.scalars(
                select(SecurityRecord).where(SecurityRecord.listing_status == "active")
            ).all()
        }
        prices = list(
            session.scalars(
                select(PriceObservation)
                .where(PriceObservation.provider_id == "vnstock")
                .order_by(PriceObservation.security_id, PriceObservation.market_session_date)
            ).all()
        )
        actions = list(session.scalars(select(CorporateActionRecord)).all())

    by_symbol: dict[int, list[PriceObservation]] = defaultdict(list)
    for row in prices:
        if row.security_id in securities:
            by_symbol[row.security_id].append(row)
    actions_by_security: dict[int, list[CorporateActionRecord]] = defaultdict(list)
    for action in actions:
        actions_by_security[action.security_id].append(action)

    anomalies: list[dict[str, object]] = []
    suspected_gaps: list[dict[str, object]] = []
    adjusted = Counter()
    source_modes = Counter()
    for security_id, bars in by_symbol.items():
        security = securities[security_id]
        for bar in bars:
            adjusted[str(bool(bar.adjusted))] += 1
            source_modes[bar.source_mode] += 1
        for previous, current in pairwise(bars):
            gap_days = (current.market_session_date - previous.market_session_date).days
            if gap_days > 4:
                suspected_gaps.append(
                    {
                        "symbol": security.symbol,
                        "from": previous.market_session_date.isoformat(),
                        "to": current.market_session_date.isoformat(),
                        "calendar_days": gap_days,
                        "status": "UNCONFIRMED",
                    }
                )
                # Do not describe a price difference across a long, unconfirmed
                # gap as a one-session move.  It needs an authorised calendar
                # before it can enter the anomaly count.
                continue
            previous_close = _as_float(previous.close)
            current_close = _as_float(current.close)
            if not previous_close or current_close is None:
                continue
            change = current_close / previous_close - 1
            if abs(change) >= args.threshold:
                effective_date = current.market_session_date
                nearby_actions = [
                    action
                    for action in actions_by_security.get(security_id, [])
                    if abs((action.effective_at.date() - effective_date).days) <= 5
                ]
                anomalies.append(
                    {
                        "symbol": security.symbol,
                        "session": effective_date.isoformat(),
                        "previous_session": previous.market_session_date.isoformat(),
                        "change_pct": round(change * 100, 4),
                        "adjusted": bool(current.adjusted),
                        "adjustment_policy": current.adjustment_policy,
                        "corporate_actions_nearby": len(nearby_actions),
                        "corporate_actions_verified": sum(
                            action.verification_status == "verified"
                            for action in nearby_actions
                        ),
                        "verification_status": "UNVERIFIED",
                    }
                )

    payload = {
        "report": "vnstock_quality_audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "vnstock",
        "price_rows": len(prices),
        "symbols": len(by_symbol),
        "anomaly_threshold_pct": args.threshold * 100,
        "anomalies": {
            "warnings": len(anomalies),
            "verified": 0,
            "unverified": len(anomalies),
            "sample": anomalies[:100],
        },
        "corporate_actions": {
            "stored_records": len(actions),
            "near_anomaly_warnings": sum(
                int(item["corporate_actions_nearby"] > 0) for item in anomalies
            ),
            "verified_near_anomaly_warnings": sum(
                int(item["corporate_actions_verified"] > 0) for item in anomalies
            ),
        },
        "adjustment_modes": dict(adjusted),
        "source_modes": dict(source_modes),
        "trading_calendar": {
            "status": "UNCONFIRMED",
            "official_calendar_source_configured": False,
            "suspected_gaps_over_four_days": len(suspected_gaps),
            "confirmed_missing_sessions": 0,
            "sample": suspected_gaps[:100],
            "note": "Weekend/holiday/session gaps need an authorised exchange calendar before being classified as missing.",
        },
        "policy": {
            "prices_modified": False,
            "warnings_excluded_from_analytics": False,
            "no_realtime_claim": True,
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

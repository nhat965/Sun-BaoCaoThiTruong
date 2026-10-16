"""HOSE securities reconciliation and guarded import.

The Vnstock reference calls are intentionally read-only until an operator
chooses the explicit import endpoint.  The two provider snapshots remain
separate in the report so a missing symbol in one source never becomes an
automatic delisting decision.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.config import Settings
from app.database import SecurityRecord, SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import Security
from app.vnstock_free import fetch_free_operation

REFERENCE_URL = "https://www.vnstocks.com/docs/vnstock/tham-chieu-reference"


async def _source_snapshot(source: str, settings: Settings) -> dict[str, Any]:
    exchange, group = await asyncio.gather(
        fetch_free_operation(
            "reference.equity_list_by_exchange",
            settings=settings,
            source=source,
            limit=5_000,
        ),
        fetch_free_operation(
            "reference.equity_list_by_group",
            settings=settings,
            source=source,
            limit=5_000,
            extra={"group": "HOSE"},
        ),
    )
    exchange_rows = [
        row for row in exchange.get("rows", [])
        if str(row.get("exchange") or "").strip().upper() == "HOSE"
        and str(row.get("symbol") or "").strip()
    ]
    group_symbols = {
        str(row.get("symbol") or "").strip().upper()
        for row in group.get("rows", [])
        if str(row.get("symbol") or "").strip()
    }
    exchange_by_symbol = {
        str(row["symbol"]).strip().upper(): row for row in exchange_rows
    }
    return {
        "source": source,
        "exchange_status": exchange.get("status"),
        "group_status": group.get("status"),
        "exchange_error": exchange.get("message") or exchange.get("error_code"),
        "group_error": group.get("message") or group.get("error_code"),
        "exchange_rows": exchange_rows,
        "exchange_symbols": set(exchange_by_symbol),
        "group_symbols": group_symbols,
        "metadata": exchange_by_symbol,
        "retrieved_at": exchange.get("retrieved_at") or group.get("retrieved_at"),
        "provenance": {
            "exchange": exchange.get("provenance", {}),
            "group": group.get("provenance", {}),
        },
    }


def _existing() -> dict[str, SecurityRecord]:
    with SessionLocal() as session:
        rows = session.scalars(select(SecurityRecord)).all()
        return {row.symbol.upper(): row for row in rows}


async def build_hose_reconciliation(settings: Settings) -> dict[str, Any]:
    snapshots = await asyncio.gather(
        _source_snapshot("vci", settings),
        _source_snapshot("kbs", settings),
    )
    by_source = {item["source"]: item for item in snapshots}
    existing = _existing()
    vci = by_source["vci"]
    kbs = by_source["kbs"]
    symbols = sorted(vci["exchange_symbols"] | kbs["exchange_symbols"])
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        vci_row = vci["metadata"].get(symbol)
        kbs_row = kbs["metadata"].get(symbol)
        current = existing.get(symbol)
        present_vci = symbol in vci["exchange_symbols"]
        present_kbs = symbol in kbs["exchange_symbols"]
        if present_vci and present_kbs:
            resolution = "both_sources"
        elif present_vci:
            resolution = "vci_only"
        else:
            resolution = "kbs_only"
        if current is not None:
            resolution = "existing_and_" + resolution
        selected = vci_row or kbs_row or {}
        rows.append(
            {
                "symbol": symbol,
                "vci": present_vci,
                "kbs": present_kbs,
                "existing_db": current is not None,
                "existing_listing_status": current.listing_status if current else None,
                "exchange": str(selected.get("exchange") or "HOSE").upper(),
                "security_type": current.security_type if current else "stock",
                "name": selected.get("organ_name") or (current.name if current else None),
                "icb_code_lv2": (vci_row or {}).get("icb_code_lv2"),
                "resolution": resolution,
            }
        )
    source_status = {
        source: {
            "exchange_status": snapshot["exchange_status"],
            "group_status": snapshot["group_status"],
            "exchange_rows": len(snapshot["exchange_rows"]),
            "group_symbols": len(snapshot["group_symbols"]),
            "exchange_group_mismatch": len(
                snapshot["exchange_symbols"] ^ snapshot["group_symbols"]
            ),
            "errors": [
                error
                for error in (snapshot["exchange_error"], snapshot["group_error"])
                if error
            ],
            "retrieved_at": snapshot["retrieved_at"],
            "provenance": snapshot["provenance"],
        }
        for source, snapshot in by_source.items()
    }
    return {
        "report": "hose_securities_reconciliation",
        "generated_at": datetime.now(UTC),
        "exchange": "HOSE",
        "sources": source_status,
        "existing_database": {
            "securities_total": len(existing),
            "hose_total": sum(1 for row in existing.values() if row.exchange.upper() == "HOSE"),
            "hose_active": sum(
                1
                for row in existing.values()
                if row.exchange.upper() == "HOSE" and row.listing_status == "active"
            ),
        },
        "summary": {
            "source_union": len(symbols),
            "both_sources": sum(1 for row in rows if row["vci"] and row["kbs"]),
            "vci_only": sum(1 for row in rows if row["vci"] and not row["kbs"]),
            "kbs_only": sum(1 for row in rows if row["kbs"] and not row["vci"]),
            "existing": sum(1 for row in rows if row["existing_db"]),
            "new": sum(1 for row in rows if not row["existing_db"]),
        },
        "rows": rows,
        "import_policy": {
            "eligible": all(
                status["exchange_status"] == "SUCCESS"
                for status in source_status.values()
            ),
            "source_preference": "vci metadata, kbs fallback",
            "notes": [
                "Absence from one provider is not treated as delisting.",
                "Only HOSE rows returned by list_by_exchange are import eligible; ETF/group-only symbols are excluded.",
                "Existing price and financial records are not deleted by the importer.",
            ],
        },
    }


async def import_hose_universe(settings: Settings) -> dict[str, Any]:
    report = await build_hose_reconciliation(settings)
    if not report["import_policy"]["eligible"]:
        raise RuntimeError("HOSE provider reconciliation is not complete; import is blocked.")
    snapshots = await asyncio.gather(
        _source_snapshot("vci", settings),
        _source_snapshot("kbs", settings),
    )
    by_source = {item["source"]: item for item in snapshots}
    vci = by_source["vci"]
    kbs = by_source["kbs"]
    now = datetime.now(UTC)
    inserted = updated = 0
    with SessionLocal() as session:
        repository = SecuritiesRepository(session)
        for symbol in sorted(vci["exchange_symbols"] | kbs["exchange_symbols"]):
            row = vci["metadata"].get(symbol) or kbs["metadata"].get(symbol)
            if not row:
                continue
            icb_code = str(row.get("icb_code_lv2") or "").strip()
            security = Security(
                symbol=symbol,
                name=str(row.get("organ_name") or symbol).strip(),
                exchange="HOSE",
                industry=f"ICB {icb_code}" if icb_code else None,
                listing_status="active",
                security_type="stock",
                provider_ids={"vnstock": symbol},
                source_name="vnstock-vci",
                source_url=REFERENCE_URL,
                last_updated=now,
            )
            _, was_inserted = repository.upsert(security)
            inserted += int(was_inserted)
            updated += int(not was_inserted)
        session.commit()
    report["import_result"] = {
        "inserted": inserted,
        "updated": updated,
        "total_after": report["summary"]["source_union"],
        "completed_at": datetime.now(UTC),
    }
    return report


def json_ready(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert sets/SQLAlchemy-free report values into JSON-friendly data."""

    return json.loads(json.dumps(payload, default=str, ensure_ascii=False))

"""Import a reconciled HOSE stock universe from the local Vnstock gateway.

The gateway performs the provider call in the already-running API process. This
keeps operator imports independent from a second Vnstock client-policy session,
while the typed importer still performs the database upsert locally. The command
requires ``--confirm`` and never uses fixture data.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import Security

REFERENCE_URL = "https://www.vnstocks.com/docs/vnstock/tham-chieu-reference"


def _get(base_url: str, operation: str, source: str) -> dict:
    query = urlencode({"source": source, "limit": 5_000})
    with urlopen(f"{base_url.rstrip('/')}/api/v1/vnstock/free/{operation}?{query}", timeout=45) as response:
        payload = json.load(response)
    if payload.get("status") != "SUCCESS":
        raise RuntimeError(
            f"{source} {operation} failed: {payload.get('message') or payload.get('error_code')}"
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=".runtime/hose_import_report.json")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to write without --confirm. Review the reconciliation first.")

    snapshots = {
        source: _get(args.api_base, "reference.equity_list_by_exchange", source)
        for source in ("vci", "kbs")
    }
    rows_by_source: dict[str, dict[str, dict]] = {}
    for source, payload in snapshots.items():
        rows_by_source[source] = {
            str(row.get("symbol") or "").strip().upper(): row
            for row in payload.get("rows", [])
            if str(row.get("exchange") or "").strip().upper() == "HOSE"
            and str(row.get("symbol") or "").strip()
        }
    symbols = sorted(set(rows_by_source["vci"]) | set(rows_by_source["kbs"]))
    if not symbols:
        raise RuntimeError("No HOSE stock rows returned by VCI/KBS.")

    now = datetime.now(UTC)
    inserted = updated = 0
    with SessionLocal() as session:
        repository = SecuritiesRepository(session)
        for symbol in symbols:
            row = rows_by_source["vci"].get(symbol) or rows_by_source["kbs"].get(symbol)
            icb_code = str(row.get("icb_code_lv2") or "").strip()
            _, was_inserted = repository.upsert(
                Security(
                    symbol=symbol,
                    name=str(row.get("organ_name") or symbol).strip(),
                    exchange="HOSE",
                    industry=f"ICB {icb_code}" if icb_code else None,
                    listing_status="active",
                    security_type="stock",
                    provider_ids={"vnstock": symbol},
                    source_name="vnstock-vci" if symbol in rows_by_source["vci"] else "vnstock-kbs",
                    source_url=REFERENCE_URL,
                    last_updated=now,
                )
            )
            inserted += int(was_inserted)
            updated += int(not was_inserted)
        session.commit()

    report = {
        "report": "hose_import_from_vnstock_gateway",
        "generated_at": now.isoformat(),
        "sources": {
            source: {"rows": len(rows)} for source, rows in rows_by_source.items()
        },
        "symbols": len(symbols),
        "inserted": inserted,
        "updated": updated,
        "provider": "vnstock",
        "mode": "live",
        "fixture": False,
        "source_url": REFERENCE_URL,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()

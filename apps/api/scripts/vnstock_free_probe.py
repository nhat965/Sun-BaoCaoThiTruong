"""Probe the documented Vnstock Community routes through the local API.

This command is read-only: it never writes the application database and never
prints credentials.  A route can still be ``FAILED`` or ``BLOCKED`` when the
selected symbol is not available, the account quota is exhausted, or the
upstream policy denies it.  That distinction is preserved in the JSON report.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

SYMBOLS = {
    "company": "HPG",
    "fundamental": "HPG",
    "index": "VN30",
    "futures": "VN30F1M",
    "warrant": "HPG",
    "etf": "E1VFVN30",
    "bond": "HPG",
    "crypto": "BTCUSDT",
    "forex": "EURUSD",
    "commodity": "XAUUSD",
    "global_index": "DJI",
    "search": "AAPL",
}


def _symbol_for(operation: str) -> str | None:
    if operation.startswith(("reference.company_", "fundamental.")):
        return SYMBOLS["fundamental"]
    if operation.startswith("reference.index_"):
        return SYMBOLS["index"]
    if operation.startswith("reference.search_"):
        return SYMBOLS["search"]
    for kind in ("futures", "warrant", "etf", "bond", "crypto", "forex", "commodity", "global_index"):
        if f"market.{kind}_" in operation:
            return SYMBOLS[kind]
    if operation == "market.multi_quote":
        return "HPG,FPT,VCB"
    if operation.startswith("market."):
        return SYMBOLS["company"]
    return None


def _request(base_url: str, operation: str, *, symbol: str | None, group: str | None, limit: int) -> dict:
    query = {"limit": limit}
    if symbol:
        query["symbol"] = symbol
    if group:
        query["group"] = group
    with urlopen(
        f"{base_url.rstrip('/')}/api/v1/vnstock/free/{operation}?{urlencode(query)}",
        timeout=60,
    ) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=".runtime/vnstock_free_probe.json")
    parser.add_argument("--operation", action="append", help="Probe only this operation; repeatable")
    parser.add_argument("--max-operations", type=int, default=42)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    args = parser.parse_args()

    with urlopen(f"{args.api_base.rstrip('/')}/api/v1/vnstock/free/catalog", timeout=30) as response:
        catalog = json.load(response)
    operations = [
        row for row in catalog.get("operations", [])
        if row.get("tier") == "Community"
        and (not args.operation or row.get("operation") in args.operation)
    ][: max(1, args.max_operations)]
    results = []
    for index, item in enumerate(operations):
        operation = item["operation"]
        group = "VN30" if item.get("requires_group") and not _symbol_for(operation) else None
        try:
            response = _request(
                args.api_base,
                operation,
                symbol=_symbol_for(operation),
                group=group,
                limit=max(1, min(args.limit, 100)),
            )
            results.append({
                "operation": operation,
                "status": response.get("status"),
                "error_code": response.get("error_code"),
                "row_count": response.get("row_count", 0),
                "source": response.get("source"),
                "route": response.get("route"),
                "metadata": response.get("metadata", {}),
                "retrieved_at": response.get("retrieved_at"),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"operation": operation, "status": "FAILED", "error_code": type(exc).__name__})
        if index + 1 < len(operations):
            time.sleep(max(0.0, args.sleep_seconds))

    report = {
        "report": "vnstock_free_route_probe",
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base": args.api_base,
        "read_only": True,
        "fixture": False,
        "routes_requested": len(operations),
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

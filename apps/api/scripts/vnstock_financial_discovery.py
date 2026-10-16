"""Probe Vnstock Finance schemas without writing to the canonical database."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from typing import Any


def _frame_summary(frame: Any) -> dict[str, Any]:
    columns = [str(column) for column in frame.columns]
    periods = sorted({str(value) for value in frame["period"].dropna().tolist()}) if "period" in frame else []
    units = sorted({str(value) for value in frame["unit"].dropna().tolist()}) if "unit" in frame else []
    nan_values = 0
    if "value" in frame:
        nan_values = sum(1 for value in frame["value"].tolist() if isinstance(value, float) and math.isnan(value))
    return {
        "rows": len(frame),
        "columns": columns,
        "periods": periods,
        "units": units,
        "nan_value_count": nan_values,
        "sample_ids": [str(value) for value in frame["id"].dropna().head(5).tolist()] if "id" in frame else [],
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="HPG,FPT,SHB,SSI")
    parser.add_argument("--sources", default="VCI,KBS")
    parser.add_argument("--periods", default="quarter,year")
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        from vnstock import Finance
    except ImportError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return

    result: dict[str, Any] = {
        "status": "DISCOVERY_ONLY",
        "symbols": {},
        "canonical_write": False,
        "notes": [
            "Community tier may limit periods; no response is written to financial_periods.",
            "Schema, units, scope and NaN values require validation before canonical mapping.",
            "Consolidated/separate scope and original/amended status are not exposed by this discovery surface.",
        ],
        "requested": {
            "symbols": [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()],
            "sources": [source.strip().upper() for source in args.sources.split(",") if source.strip()],
            "periods": [period.strip().lower() for period in args.periods.split(",") if period.strip()],
        },
    }
    successful_reports = 0
    for symbol in result["requested"]["symbols"]:
        for source in result["requested"]["sources"]:
            for period in result["requested"]["periods"]:
                key = f"{symbol}@{source}@{period}"
                try:
                    finance = Finance(source=source, symbol=symbol, period=period, get_all=True, show_log=False)
                    reports: dict[str, Any] = {}
                    for name in ("income_statement", "balance_sheet", "cash_flow"):
                        try:
                            reports[name] = _frame_summary(getattr(finance, name)())
                            successful_reports += 1
                        except Exception as exc:  # noqa: BLE001 - provider/schema diagnostics only
                            reports[name] = {"error": f"{type(exc).__name__}: {str(exc)[:180]}"}
                        if args.pause_seconds:
                            time.sleep(args.pause_seconds)
                    result["symbols"][key] = reports
                except Exception as exc:  # noqa: BLE001 - provider diagnostics only
                    result["symbols"][key] = {"init_error": f"{type(exc).__name__}: {str(exc)[:180]}"}
    if successful_reports == 0:
        result["status"] = "BLOCKED"
        result["blocker"] = "No financial response succeeded during this probe; inspect per-symbol errors."
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()

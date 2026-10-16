"""Import an operator-authorized daily OHLCV CSV into the local database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.authorized_market_data import import_authorized_prices, preview_authorized_prices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--source-name", default="authorized-ohlcv-file")
    parser.add_argument("--preview", action="store_true", help="validate without writing")
    args = parser.parse_args()
    content = args.csv_file.read_text(encoding="utf-8-sig")
    result = (
        preview_authorized_prices(content, args.source_name)
        if args.preview
        else import_authorized_prices(content, args.source_name)
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.validation_status != "rejected" else 1


if __name__ == "__main__":
    sys.exit(main())

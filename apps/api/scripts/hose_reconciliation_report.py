"""Save a VCI/KBS HOSE reconciliation from the local API gateway."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=".runtime/hose_reconciliation.json")
    args = parser.parse_args()
    with urlopen(
        f"{args.api_base.rstrip('/')}/api/v1/data-platform/hose/reconciliation",
        timeout=60,
    ) as response:
        payload = json.load(response)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()

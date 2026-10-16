"""Print the persisted-data reconciliation report as JSON.

This is read-only and intentionally does not call an external provider.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.reconciliation import build_reconciliation_report

if __name__ == "__main__":
    print(json.dumps(build_reconciliation_report(get_settings()), default=str, indent=2))

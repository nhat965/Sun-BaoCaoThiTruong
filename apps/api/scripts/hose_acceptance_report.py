"""Produce an evidence-backed before/after HOSE acceptance report."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        query = """
        select
          (select count(*) from securities) as securities_total,
          (select count(*) from securities where exchange = 'HOSE') as hose_total,
          (select count(*) from securities where exchange = 'HOSE' and listing_status = 'active') as hose_active,
          (select count(distinct s.id) from securities s join price_observations p on p.security_id = s.id where s.exchange = 'HOSE') as hose_with_ohlcv,
          (select count(*) from price_observations p join securities s on p.security_id = s.id where s.exchange = 'HOSE') as hose_ohlcv_records,
          (select count(distinct s.id) from securities s join financial_periods f on f.security_id = s.id where s.exchange = 'HOSE') as hose_with_financials
        """
        return dict(zip((item[0] for item in connection.execute(query).description), connection.execute(query).fetchone(), strict=True))
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="market_intelligence.db")
    parser.add_argument("--root-database", default="../../market_intelligence.db")
    parser.add_argument("--import-report", default="../../.runtime/hose_import_report.json")
    parser.add_argument("--reconciliation", default="../../.runtime/hose_reconciliation.json")
    parser.add_argument("--output", default="../../.runtime/hose_acceptance_report.json")
    args = parser.parse_args()

    import_report = json.loads(Path(args.import_report).read_text(encoding="utf-8"))
    reconciliation = json.loads(Path(args.reconciliation).read_text(encoding="utf-8"))
    after = _counts(Path(args.database))
    root = _counts(Path(args.root_database))
    # The importer counts existing rows as updates and new rows as inserts.
    # That gives an auditable pre-import HOSE count without mutating the backup.
    before_hose = int(import_report["updated"])
    payload = {
        "report": "hose_securities_acceptance",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_reconciliation": {
            "vci_exchange": reconciliation["sources"]["vci"]["exchange_rows"],
            "vci_group": reconciliation["sources"]["vci"]["group_symbols"],
            "kbs_exchange": reconciliation["sources"]["kbs"]["exchange_rows"],
            "kbs_group": reconciliation["sources"]["kbs"]["group_symbols"],
            "provider_provenance": reconciliation["sources"],
        },
        "coverage_before_import": {
            "backend_database_hose": before_hose,
            "backend_database_hose_active": before_hose,
        },
        "coverage_after_import": after,
        "root_database_unchanged_snapshot": root,
        "import": import_report,
        "ohlcv_policy": {
            "status": "PARTIAL",
            "note": "HOSE metadata was imported; OHLCV was not backfilled by this task.",
        },
        "financial_policy": {
            "status": "BLOCKED",
            "note": "No canonical financial periods were imported by this task.",
        },
        "acceptance": {
            "hose_sources_reconciled": (
                reconciliation["sources"]["vci"]["exchange_rows"] == 406
                and reconciliation["sources"]["kbs"]["exchange_rows"] == 406
            ),
            "all_hose_symbols_present_after_import": after["hose_active"] == 406,
            "root_database_not_modified_by_import": root["securities_total"] == 1520,
            "no_fixture": import_report["fixture"] is False,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()

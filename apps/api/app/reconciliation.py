"""Read-only reconciliation report for imported and synchronized datasets."""

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import Settings
from app.data_capabilities import build_capability_audit
from app.database import (
    CorporateActionRecord,
    DataSyncErrorRecord,
    DataSyncRunRecord,
    FinancialPeriodRecord,
    MarketIndexObservationRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
)


def _group_rows(rows, provider_getter, timestamp_getter, valid_getter=None):
    groups = defaultdict(list)
    for row in rows:
        groups[provider_getter(row) or "unknown"].append(row)
    result = []
    for provider, values in sorted(groups.items()):
        timestamps = [timestamp_getter(item) for item in values if timestamp_getter(item)]
        valid = sum(valid_getter(item) for item in values) if valid_getter else None
        symbols = {
            getattr(item, "symbol", None) or getattr(item, "provider_symbol", None)
            for item in values
            if getattr(item, "symbol", None) or getattr(item, "provider_symbol", None)
        }
        result.append(
            {
                "provider": provider,
                "records": len(values),
                "symbols": len(symbols) if symbols else None,
                "valid_records": valid,
                "invalid_records": len(values) - valid if valid is not None else None,
                "last_update": max(timestamps) if timestamps else None,
            }
        )
    return result


def build_reconciliation_report(settings: Settings) -> dict:
    """Compare persisted counts, validation, and latest sync evidence.

    The report does not reconcile against an external source; it explicitly
    reports that missing external baselines remain a blocker.
    """
    with SessionLocal() as session:
        securities = list(session.scalars(select(SecurityRecord)).all())
        prices = list(session.scalars(select(PriceObservation)).all())
        indices = list(session.scalars(select(MarketIndexObservationRecord)).all())
        financials = list(session.scalars(select(FinancialPeriodRecord)).all())
        actions = list(session.scalars(select(CorporateActionRecord)).all())
        runs = list(
            session.scalars(
                select(DataSyncRunRecord).order_by(DataSyncRunRecord.finished_at.desc())
            ).all()
        )
        errors = list(session.scalars(select(DataSyncErrorRecord)).all())

    latest_runs: dict[str, DataSyncRunRecord] = {}
    for run in runs:
        latest_runs.setdefault(run.capability, run)

    datasets = [
        {
            "dataset": "securities",
            "groups": _group_rows(
                securities, lambda row: row.source_name, lambda row: row.last_updated,
                lambda row: bool(row.name and row.exchange and row.symbol),
            ),
            "records_before": None,
            "records_after": len(securities),
            "missing_external_baseline": True,
        },
        {
            "dataset": "ohlcv",
            "groups": _group_rows(
                prices, lambda row: row.provider, lambda row: row.ingested_at,
                lambda row: row.validation_status in {"valid", "partial"},
            ),
            "records_before": None,
            "records_after": len(prices),
            "missing_external_baseline": True,
        },
        {
            "dataset": "indices",
            "groups": _group_rows(
                indices, lambda row: row.provider, lambda row: row.retrieved_at,
                lambda row: row.validation_status in {"valid", "partial"},
            ),
            "records_before": None,
            "records_after": len(indices),
            "missing_external_baseline": True,
        },
        {
            "dataset": "financials",
            "groups": _group_rows(
                financials, lambda row: row.source_name, lambda row: row.retrieved_at,
                lambda row: row.verification_status in {"verified", "partially_verified", "unverified"},
            ),
            "records_before": None,
            "records_after": len(financials),
            "missing_external_baseline": True,
        },
        {
            "dataset": "corporate_actions",
            "groups": _group_rows(
                actions, lambda row: row.source_name, lambda row: row.retrieved_at,
                lambda row: row.verification_status == "verified",
            ),
            "records_before": None,
            "records_after": len(actions),
            "missing_external_baseline": True,
        },
    ]
    capability_rows = build_capability_audit(settings)["capabilities"]
    for dataset in datasets:
        capability = {
            "securities": "securities_metadata",
            "ohlcv": "historical_ohlcv",
            "indices": "market_indices",
            "financials": "financial_statements",
            "corporate_actions": "corporate_actions",
        }[dataset["dataset"]]
        row = next(
            item for item in capability_rows
            if item["capability"] == capability
        )
        dataset.update(
            {
                "coverage_status": row["status"],
                "verification": row["verification"],
                "license_rights": row["license_rights"],
                "blocker": row["blocker"],
                "last_successful_sync": (
                    latest_runs[capability].finished_at if capability in latest_runs else None
                ),
            }
        )

    return {
        "generated_at": datetime.now(UTC),
        "datasets": datasets,
        "sync_runs": len(runs),
        "sync_errors": len(errors),
        "unresolved_external_baseline": True,
        "limitations": [
            "records_before is null because no external snapshot was supplied",
            "reconciliation validates internal consistency and provenance, not market truth",
            "PDF/manual source content remains unverified until operator review",
        ],
    }

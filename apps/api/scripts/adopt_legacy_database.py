"""Safely attach an unversioned MVP database to the Alembic migration chain."""

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from alembic import command
from app.database import engine

BASELINE_COLUMNS = {
    "securities": {"id", "symbol", "name", "exchange", "currency"},
    "price_observations": {
        "id",
        "security_id",
        "provider",
        "provider_symbol",
        "market_timestamp",
        "ingested_at",
        "interval",
        "close",
        "volume",
        "adjusted",
    },
    "analysis_runs": {
        "id",
        "symbol",
        "status",
        "formula_version",
        "source_name",
        "coverage",
        "provenance_json",
        "created_at",
    },
    "generated_reports": {
        "id",
        "analysis_run_id",
        "format",
        "storage_key",
        "created_at",
    },
}

V2_COLUMNS = {
    "securities": BASELINE_COLUMNS["securities"]
    | {
        "normalized_name",
        "aliases_json",
        "industry",
        "sector",
        "listing_status",
        "security_type",
        "provider_ids_json",
        "source_name",
        "source_url",
        "last_updated",
    },
    "price_observations": BASELINE_COLUMNS["price_observations"]
    | {"open", "high", "low", "currency", "validation_status", "adjustment_policy"},
    "source_health": {
        "id",
        "source_name",
        "status",
        "checked_at",
        "latency_ms",
        "message",
        "consecutive_failures",
    },
}

V4_COLUMNS = V2_COLUMNS | {
    "audit_logs": {
        "id",
        "actor",
        "action",
        "resource",
        "outcome",
        "source_ip",
        "metadata_json",
        "created_at",
    },
    "financial_periods": {
        "id",
        "security_id",
        "period_end",
        "period_type",
        "fiscal_year",
        "source_name",
        "updated_at",
    },
    "financial_statement_items": {
        "id",
        "period_id",
        "statement_type",
        "item_code",
        "value",
        "source_name",
        "updated_at",
    },
    "financial_metrics": {
        "id",
        "security_id",
        "metric_name",
        "value",
        "formula_version",
        "source_name",
        "calculated_at",
    },
    "valuation_results": {
        "id",
        "security_id",
        "method",
        "scenario",
        "value",
        "assumptions_json",
        "source_name",
        "created_at",
    },
    "corporate_actions": {
        "id",
        "security_id",
        "action_type",
        "effective_at",
        "source_name",
        "retrieved_at",
    },
}


def has_columns(inspector, requirements: dict[str, set[str]]) -> bool:
    tables = set(inspector.get_table_names())
    if not set(requirements).issubset(tables):
        return False
    return all(
        required.issubset({column["name"] for column in inspector.get_columns(table)})
        for table, required in requirements.items()
    )


def main() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if not tables:
        print("Database is empty; run `alembic upgrade head` directly.")
        return

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    alembic_config = Config(str(config_path))
    alembic_config.set_main_option("script_location", str(config_path.parent / "alembic"))

    if has_columns(inspector, V4_COLUMNS):
        if current_revision != "0004":
            command.stamp(alembic_config, "0004")
            print("Verified the V3 schema and stamped it at Alembic revision 0004.")
        else:
            print("Database is already at Alembic revision 0004; no adoption needed.")
        return

    if current_revision:
        print(f"Database is already at Alembic revision {current_revision}; no adoption needed.")
        return

    if has_columns(inspector, V2_COLUMNS):
        command.stamp(alembic_config, "0002")
        print("Verified the V2 schema and stamped it at Alembic revision 0002.")
        return

    if current_revision:
        print(f"Database is already at Alembic revision {current_revision}; no adoption needed.")
        return

    missing_tables = set(BASELINE_COLUMNS) - tables
    if missing_tables:
        names = ", ".join(sorted(missing_tables))
        raise SystemExit(f"Refusing adoption: missing baseline tables: {names}")

    for table, required_columns in BASELINE_COLUMNS.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table)}
        missing_columns = required_columns - actual_columns
        if missing_columns:
            names = ", ".join(sorted(missing_columns))
            raise SystemExit(f"Refusing adoption: {table} is missing columns: {names}")

    command.stamp(alembic_config, "0001")
    print("Verified the legacy MVP schema and stamped it at Alembic revision 0001.")
    print("Next: run `alembic upgrade head`.")


if __name__ == "__main__":
    main()

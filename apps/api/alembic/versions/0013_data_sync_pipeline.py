"""add provider sync runs and raw financial units"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("financial_statement_items") as batch:
        batch.add_column(sa.Column("raw_value", sa.Numeric(28, 6), nullable=True))
        batch.add_column(sa.Column("raw_unit", sa.String(32), nullable=True))

    op.create_table(
        "data_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=True),
        sa.Column("sync_mode", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
    )
    for column in ("provider", "capability", "symbol", "status", "started_at"):
        op.create_index(f"ix_data_sync_runs_{column}", "data_sync_runs", [column])

    op.create_table(
        "data_sync_errors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("data_sync_runs.id"), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("message", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("run_id", "symbol", "error_code", "created_at"):
        op.create_index(f"ix_data_sync_errors_{column}", "data_sync_errors", [column])


def downgrade():
    op.drop_table("data_sync_errors")
    op.drop_table("data_sync_runs")
    with op.batch_alter_table("financial_statement_items") as batch:
        batch.drop_column("raw_unit")
        batch.drop_column("raw_value")

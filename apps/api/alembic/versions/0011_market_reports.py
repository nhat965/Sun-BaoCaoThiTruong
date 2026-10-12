"""add source mode and deterministic report snapshots"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
        batch.create_index("ix_jobs_next_attempt_at", ["next_attempt_at"])
    with op.batch_alter_table("price_observations") as batch:
        batch.add_column(
            sa.Column(
                "source_mode", sa.String(16), nullable=False, server_default="unknown"
            )
        )
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_key", sa.String(128), nullable=False, unique=True),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(16)),
        sa.Column("trading_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_mode", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_snapshots_snapshot_key", "report_snapshots", ["snapshot_key"], unique=True)
    op.create_index("ix_report_snapshots_report_type", "report_snapshots", ["report_type"])
    op.create_index("ix_report_snapshots_symbol", "report_snapshots", ["symbol"])
    op.create_index("ix_report_snapshots_trading_date", "report_snapshots", ["trading_date"])


def downgrade():
    op.drop_table("report_snapshots")
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_column("source_mode")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_index("ix_jobs_next_attempt_at")
        batch.drop_column("next_attempt_at")

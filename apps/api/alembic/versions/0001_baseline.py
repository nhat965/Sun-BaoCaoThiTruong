"""baseline audit schema"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "securities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
    )
    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_symbol", sa.String(32), nullable=False),
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(16), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("adjusted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("formula_version", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("coverage", sa.String(24), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_runs_symbol", "analysis_runs", ["symbol"])
    op.create_table(
        "generated_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False
        ),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("generated_reports")
    op.drop_index("ix_analysis_runs_symbol", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_table("price_observations")
    op.drop_table("securities")

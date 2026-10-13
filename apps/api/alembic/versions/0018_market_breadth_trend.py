"""persist market breadth and regime snapshots"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _snapshot_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_session_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False, server_default="canonical-price-selection"),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("data_mode", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="unvalidated"),
        sa.Column("coverage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("divergences_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("formula_version", sa.String(32), nullable=False, server_default="market-breadth-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "market_session_date",
            "formula_version",
            name="uq_market_breadth_session_formula",
        ),
    ]


def _regime_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_session_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False, server_default="canonical-price-selection"),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("data_mode", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="unvalidated"),
        sa.Column("coverage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("indicators_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("conflicts_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("formula_version", sa.String(32), nullable=False, server_default="market-regime-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "market_session_date",
            "formula_version",
            name="uq_market_regime_session_formula",
        ),
    ]


def upgrade():
    op.create_table("market_breadth_snapshots", *_snapshot_columns())
    op.create_index(
        "ix_market_breadth_snapshots_market_session_date",
        "market_breadth_snapshots",
        ["market_session_date"],
    )
    op.create_index(
        "ix_market_breadth_snapshots_as_of", "market_breadth_snapshots", ["as_of"]
    )
    op.create_table("market_regime_snapshots", *_regime_columns())
    op.create_index(
        "ix_market_regime_snapshots_market_session_date",
        "market_regime_snapshots",
        ["market_session_date"],
    )
    op.create_index(
        "ix_market_regime_snapshots_as_of", "market_regime_snapshots", ["as_of"]
    )
    op.create_index(
        "ix_market_regime_snapshots_regime", "market_regime_snapshots", ["regime"]
    )


def downgrade():
    op.drop_index("ix_market_regime_snapshots_regime", table_name="market_regime_snapshots")
    op.drop_index("ix_market_regime_snapshots_as_of", table_name="market_regime_snapshots")
    op.drop_index(
        "ix_market_regime_snapshots_market_session_date", table_name="market_regime_snapshots"
    )
    op.drop_table("market_regime_snapshots")
    op.drop_index("ix_market_breadth_snapshots_as_of", table_name="market_breadth_snapshots")
    op.drop_index(
        "ix_market_breadth_snapshots_market_session_date", table_name="market_breadth_snapshots"
    )
    op.drop_table("market_breadth_snapshots")

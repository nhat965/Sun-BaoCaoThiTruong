"""persist sector and liquidity intelligence snapshots"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _common_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_session_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False, server_default="canonical-price-selection"),
        sa.Column("data_mode", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="unvalidated"),
        sa.Column("coverage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("formula_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    sector_columns = [
        sa.Column("sector_id", sa.String(128), nullable=False),
        sa.Column("sector_name", sa.String(128), nullable=False),
        sa.Column("taxonomy_version", sa.String(32), nullable=False, server_default="registry-v1"),
        *_common_columns(),
        sa.UniqueConstraint(
            "sector_id",
            "market_session_date",
            "formula_version",
            name="uq_sector_snapshot_session_formula",
        ),
    ]
    op.create_table("sector_snapshots", *sector_columns)
    op.create_index("ix_sector_snapshots_sector_id", "sector_snapshots", ["sector_id"])
    op.create_index(
        "ix_sector_snapshots_market_session_date", "sector_snapshots", ["market_session_date"]
    )
    op.create_index("ix_sector_snapshots_as_of", "sector_snapshots", ["as_of"])

    liquidity_columns = [
        *_common_columns(),
        sa.UniqueConstraint(
            "market_session_date",
            "formula_version",
            name="uq_liquidity_snapshot_session_formula",
        ),
    ]
    op.create_table("liquidity_snapshots", *liquidity_columns)
    op.create_index(
        "ix_liquidity_snapshots_market_session_date",
        "liquidity_snapshots",
        ["market_session_date"],
    )
    op.create_index("ix_liquidity_snapshots_as_of", "liquidity_snapshots", ["as_of"])


def downgrade():
    op.drop_index("ix_liquidity_snapshots_as_of", table_name="liquidity_snapshots")
    op.drop_index(
        "ix_liquidity_snapshots_market_session_date", table_name="liquidity_snapshots"
    )
    op.drop_table("liquidity_snapshots")
    op.drop_index("ix_sector_snapshots_as_of", table_name="sector_snapshots")
    op.drop_index(
        "ix_sector_snapshots_market_session_date", table_name="sector_snapshots"
    )
    op.drop_index("ix_sector_snapshots_sector_id", table_name="sector_snapshots")
    op.drop_table("sector_snapshots")

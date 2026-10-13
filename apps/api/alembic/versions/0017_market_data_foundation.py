"""add market index provenance and extended price-quality metadata"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("price_observations") as batch:
        batch.add_column(sa.Column("actual_trading_value", sa.Numeric(28, 6), nullable=True))
        batch.add_column(sa.Column("market_cap", sa.Numeric(28, 6), nullable=True))
        batch.add_column(sa.Column("source_url", sa.String(1024), nullable=True))
        batch.add_column(
            sa.Column("coverage", sa.String(32), nullable=False, server_default="security")
        )
        batch.add_column(
            sa.Column("freshness", sa.String(32), nullable=False, server_default="unknown")
        )
        batch.add_column(sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "market_index_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("market_session_date", sa.Date(), nullable=False),
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("previous_close", sa.Numeric(20, 6), nullable=True),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_mode", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column(
            "validation_status", sa.String(24), nullable=False, server_default="unvalidated"
        ),
        sa.Column("coverage", sa.String(32), nullable=False, server_default="index"),
        sa.Column("freshness", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("adjustment_policy", sa.String(128), nullable=False, server_default="unknown"),
        sa.UniqueConstraint(
            "symbol", "provider_id", "market_session_date", name="uq_market_index_provider_session"
        ),
    )
    op.create_index("ix_market_index_observations_symbol", "market_index_observations", ["symbol"])
    op.create_index(
        "ix_market_index_observations_exchange", "market_index_observations", ["exchange"]
    )
    op.create_index(
        "ix_market_index_observations_market_session_date",
        "market_index_observations",
        ["market_session_date"],
    )
    op.create_index(
        "ix_market_index_observations_market_timestamp",
        "market_index_observations",
        ["market_timestamp"],
    )
    op.create_index(
        "ix_market_index_observations_provider", "market_index_observations", ["provider"]
    )
    op.create_index(
        "ix_market_index_observations_provider_id", "market_index_observations", ["provider_id"]
    )
    op.create_index(
        "ix_market_index_observations_retrieved_at", "market_index_observations", ["retrieved_at"]
    )


def downgrade():
    op.drop_index("ix_market_index_observations_retrieved_at", table_name="market_index_observations")
    op.drop_index("ix_market_index_observations_provider_id", table_name="market_index_observations")
    op.drop_index("ix_market_index_observations_provider", table_name="market_index_observations")
    op.drop_index(
        "ix_market_index_observations_market_timestamp", table_name="market_index_observations"
    )
    op.drop_index(
        "ix_market_index_observations_market_session_date", table_name="market_index_observations"
    )
    op.drop_index("ix_market_index_observations_exchange", table_name="market_index_observations")
    op.drop_index("ix_market_index_observations_symbol", table_name="market_index_observations")
    op.drop_table("market_index_observations")
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_column("last_updated")
        batch.drop_column("freshness")
        batch.drop_column("coverage")
        batch.drop_column("source_url")
        batch.drop_column("market_cap")
        batch.drop_column("actual_trading_value")

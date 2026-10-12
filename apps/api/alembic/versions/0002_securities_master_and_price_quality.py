"""securities master and validated OHLCV storage"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("securities") as batch:
        batch.add_column(
            sa.Column("normalized_name", sa.String(255), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("aliases_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("industry", sa.String(128), nullable=True))
        batch.add_column(sa.Column("sector", sa.String(128), nullable=True))
        batch.add_column(
            sa.Column("listing_status", sa.String(24), nullable=False, server_default="active")
        )
        batch.add_column(
            sa.Column("security_type", sa.String(32), nullable=False, server_default="stock")
        )
        batch.add_column(
            sa.Column("provider_ids_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("source_name", sa.String(128), nullable=False, server_default="migration")
        )
        batch.add_column(sa.Column("source_url", sa.String(1024), nullable=True))
        batch.add_column(
            sa.Column(
                "last_updated",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.create_index("ix_securities_exchange", ["exchange"])
        batch.create_index("ix_securities_listing_status", ["listing_status"])
        batch.create_index("ix_securities_normalized_name", ["normalized_name"])

    with op.batch_alter_table("price_observations") as batch:
        batch.add_column(sa.Column("open", sa.Numeric(20, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("high", sa.Numeric(20, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("low", sa.Numeric(20, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("currency", sa.String(8), nullable=False, server_default="VND"))
        batch.add_column(
            sa.Column("validation_status", sa.String(24), nullable=False, server_default="partial")
        )
        batch.add_column(
            sa.Column(
                "adjustment_policy", sa.String(64), nullable=False, server_default="unadjusted"
            )
        )
        batch.create_index("ix_price_observations_security_id", ["security_id"])
        batch.create_index("ix_price_observations_provider", ["provider"])
        batch.create_index("ix_price_observations_market_timestamp", ["market_timestamp"])
        batch.create_unique_constraint(
            "uq_price_point", ["security_id", "provider", "market_timestamp", "interval"]
        )

    op.create_table(
        "source_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(512), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("source_health")
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_constraint("uq_price_point", type_="unique")
        batch.drop_index("ix_price_observations_market_timestamp")
        batch.drop_index("ix_price_observations_provider")
        batch.drop_index("ix_price_observations_security_id")
        for column in ("adjustment_policy", "validation_status", "currency", "low", "high", "open"):
            batch.drop_column(column)
    with op.batch_alter_table("securities") as batch:
        batch.drop_index("ix_securities_normalized_name")
        batch.drop_index("ix_securities_listing_status")
        batch.drop_index("ix_securities_exchange")
        for column in (
            "last_updated",
            "source_url",
            "source_name",
            "provider_ids_json",
            "security_type",
            "listing_status",
            "sector",
            "industry",
            "aliases_json",
            "normalized_name",
        ):
            batch.drop_column(column)

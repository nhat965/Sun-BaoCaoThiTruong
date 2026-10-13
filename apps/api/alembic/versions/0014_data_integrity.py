"""add canonical market sessions and financial validation versions"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("price_observations") as batch:
        batch.add_column(
            sa.Column("provider_id", sa.String(64), nullable=False, server_default="unknown")
        )
        batch.add_column(sa.Column("market_session_date", sa.Date(), nullable=True))
        batch.create_index("ix_price_observations_provider_id", ["provider_id"])
        batch.create_index(
            "ix_price_observations_market_session_date", ["market_session_date"]
        )
    op.execute(
        sa.text(
            "UPDATE price_observations "
            "SET market_session_date = CAST(market_timestamp AS DATE) "
            "WHERE market_session_date IS NULL"
        )
    )
    with op.batch_alter_table("price_observations") as batch:
        batch.alter_column("market_session_date", existing_type=sa.Date(), nullable=False)
        batch.create_unique_constraint(
            "uq_price_provider_session",
            [
                "security_id",
                "provider_id",
                "market_session_date",
                "interval",
                "adjusted",
            ],
        )

    with op.batch_alter_table("financial_periods") as batch:
        batch.drop_constraint("uq_financial_period_scope", type_="unique")
        batch.create_unique_constraint(
            "uq_financial_period_scope",
            [
                "security_id",
                "period_end",
                "period_type",
                "statement_scope",
                "statement_status",
            ],
        )

    op.create_table(
        "financial_validation_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("financial_periods.id"), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False),
        sa.Column("statement_scope", sa.String(24), nullable=False),
        sa.Column("statement_status", sa.String(24), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("checks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("errors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("validation_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("security_id", "period_id", "period_end", "validation_status"):
        op.create_index(
            f"ix_financial_validation_reports_{column}",
            "financial_validation_reports",
            [column],
        )


def downgrade():
    op.drop_table("financial_validation_reports")
    with op.batch_alter_table("financial_periods") as batch:
        batch.drop_constraint("uq_financial_period_scope", type_="unique")
        batch.create_unique_constraint(
            "uq_financial_period_scope",
            ["security_id", "period_end", "period_type", "statement_scope"],
        )
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_constraint("uq_price_provider_session", type_="unique")
        batch.drop_index("ix_price_observations_market_session_date")
        batch.drop_index("ix_price_observations_provider_id")
        batch.drop_column("market_session_date")
        batch.drop_column("provider_id")

"""add manual portfolio and transaction ledger"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("base_currency", sa.String(8), nullable=False, server_default="VND"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("transaction_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 6), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(28, 6), nullable=False, server_default="0"),
        sa.Column("fees", sa.Numeric(28, 6), nullable=False, server_default="0"),
        sa.Column("cash_amount", sa.Numeric(28, 6), nullable=False, server_default="0"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("portfolio_id", "external_id", name="uq_portfolio_external_id"),
    )
    op.create_index("ix_portfolio_transactions_portfolio_id", "portfolio_transactions", ["portfolio_id"])
    op.create_index("ix_portfolio_transactions_symbol", "portfolio_transactions", ["symbol"])
    op.create_index("ix_portfolio_transactions_transaction_type", "portfolio_transactions", ["transaction_type"])
    op.create_index("ix_portfolio_transactions_executed_at", "portfolio_transactions", ["executed_at"])


def downgrade():
    op.drop_table("portfolio_transactions")
    op.drop_table("portfolios")

"""financial statement storage, metrics, valuations and corporate actions"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column(
            "verification_status", sa.String(24), nullable=False, server_default="unverified"
        ),
        sa.Column("unit", sa.String(32), nullable=False, server_default="VND"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="VND"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("security_id", "period_end", "period_type"),
    )
    op.create_index("ix_financial_periods_security_id", "financial_periods", ["security_id"])
    op.create_index("ix_financial_periods_period_end", "financial_periods", ["period_end"])
    op.create_index("ix_financial_periods_period_type", "financial_periods", ["period_type"])
    op.create_table(
        "financial_statement_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("financial_periods.id"), nullable=False),
        sa.Column("statement_type", sa.String(24), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(28, 6), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False, server_default="VND"),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column(
            "verification_status", sa.String(24), nullable=False, server_default="unverified"
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("period_id", "statement_type", "item_code"),
    )
    op.create_index(
        "ix_financial_statement_items_period_id", "financial_statement_items", ["period_id"]
    )
    op.create_index(
        "ix_financial_statement_items_statement_type",
        "financial_statement_items",
        ["statement_type"],
    )
    op.create_index(
        "ix_financial_statement_items_item_code", "financial_statement_items", ["item_code"]
    )
    op.create_table(
        "financial_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("financial_periods.id"), nullable=True),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(28, 6), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default="ratio"),
        sa.Column("formula_version", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_financial_metrics_security_id", "financial_metrics", ["security_id"])
    op.create_index("ix_financial_metrics_period_id", "financial_metrics", ["period_id"])
    op.create_index("ix_financial_metrics_metric_name", "financial_metrics", ["metric_name"])
    op.create_table(
        "valuation_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("scenario", sa.String(16), nullable=False),
        sa.Column("value", sa.Numeric(28, 6), nullable=True),
        sa.Column("assumptions_json", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("security_id", "method", "scenario", "created_at"),
    )
    op.create_index("ix_valuation_results_security_id", "valuation_results", ["security_id"])
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ratio", sa.Numeric(20, 8), nullable=True),
        sa.Column("cash_amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column(
            "verification_status", sa.String(24), nullable=False, server_default="unverified"
        ),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("security_id", "action_type", "effective_at", "source_name"),
    )
    op.create_index("ix_corporate_actions_security_id", "corporate_actions", ["security_id"])
    op.create_index("ix_corporate_actions_effective_at", "corporate_actions", ["effective_at"])


def downgrade():
    op.drop_index("ix_corporate_actions_effective_at", table_name="corporate_actions")
    op.drop_index("ix_corporate_actions_security_id", table_name="corporate_actions")
    op.drop_table("corporate_actions")
    op.drop_index("ix_valuation_results_security_id", table_name="valuation_results")
    op.drop_table("valuation_results")
    op.drop_index("ix_financial_metrics_metric_name", table_name="financial_metrics")
    op.drop_index("ix_financial_metrics_period_id", table_name="financial_metrics")
    op.drop_index("ix_financial_metrics_security_id", table_name="financial_metrics")
    op.drop_table("financial_metrics")
    op.drop_index("ix_financial_statement_items_item_code", table_name="financial_statement_items")
    op.drop_index(
        "ix_financial_statement_items_statement_type", table_name="financial_statement_items"
    )
    op.drop_index("ix_financial_statement_items_period_id", table_name="financial_statement_items")
    op.drop_table("financial_statement_items")
    op.drop_index("ix_financial_periods_period_type", table_name="financial_periods")
    op.drop_index("ix_financial_periods_period_end", table_name="financial_periods")
    op.drop_index("ix_financial_periods_security_id", table_name="financial_periods")
    op.drop_table("financial_periods")

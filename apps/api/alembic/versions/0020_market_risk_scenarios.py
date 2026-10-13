"""persist market risk signals and conditional scenarios"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    common = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_session_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False, server_default="canonical-price-selection"),
        sa.Column("data_mode", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="unvalidated"),
        sa.Column("formula_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]
    op.create_table("market_risk_signals", sa.Column("signal_id", sa.String(64), nullable=False), sa.Column("signal_type", sa.String(32), nullable=False), sa.Column("severity", sa.String(16), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("trigger_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"), *common, sa.UniqueConstraint("market_session_date", "signal_id", "formula_version", name="uq_market_risk_signal_session"))
    op.create_index("ix_market_risk_signals_signal_id", "market_risk_signals", ["signal_id"])
    op.create_index("ix_market_risk_signals_market_session_date", "market_risk_signals", ["market_session_date"])
    op.create_table("market_scenario_snapshots", sa.Column("scenario_id", sa.String(24), nullable=False), sa.Column("label", sa.String(128), nullable=False), sa.Column("assumptions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("invalidation_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("risks_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("watch_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("data_status", sa.String(16), nullable=False, server_default="unavailable"), *common, sa.UniqueConstraint("market_session_date", "scenario_id", "formula_version", name="uq_market_scenario_session"))
    op.create_index("ix_market_scenario_snapshots_scenario_id", "market_scenario_snapshots", ["scenario_id"])
    op.create_index("ix_market_scenario_snapshots_market_session_date", "market_scenario_snapshots", ["market_session_date"])


def downgrade():
    op.drop_index("ix_market_scenario_snapshots_market_session_date", table_name="market_scenario_snapshots")
    op.drop_index("ix_market_scenario_snapshots_scenario_id", table_name="market_scenario_snapshots")
    op.drop_table("market_scenario_snapshots")
    op.drop_index("ix_market_risk_signals_market_session_date", table_name="market_risk_signals")
    op.drop_index("ix_market_risk_signals_signal_id", table_name="market_risk_signals")
    op.drop_table("market_risk_signals")

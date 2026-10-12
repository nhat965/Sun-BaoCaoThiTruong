"""idempotent jobs, watchlists and alert persistence"""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_type", sa.String(32), nullable=False), sa.Column("symbol", sa.String(16), nullable=False), sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="QUEUED"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("last_error", sa.String(1024)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("job_type", "symbol", "scheduled_for", name="uq_job_idempotency"))
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"]); op.create_index("ix_jobs_symbol", "jobs", ["symbol"]); op.create_index("ix_jobs_scheduled_for", "jobs", ["scheduled_for"]); op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table("job_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("error", sa.String(1024)), sa.Column("result_json", sa.Text(), nullable=False, server_default="{}")); op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_table("watchlists", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(128), nullable=False, unique=True), sa.Column("owner", sa.String(128), nullable=False, server_default="local"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("watchlist_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id"), nullable=False), sa.Column("symbol", sa.String(16), nullable=False), sa.Column("added_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbol")); op.create_index("ix_watchlist_items_watchlist_id", "watchlist_items", ["watchlist_id"]); op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"])
    op.create_table("alert_rules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id"), nullable=False), sa.Column("rule_type", sa.String(32), nullable=False), sa.Column("threshold", sa.Numeric(20, 6)), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)); op.create_index("ix_alert_rules_watchlist_id", "alert_rules", ["watchlist_id"])
    op.create_table("alerts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("rule_id", sa.Integer(), sa.ForeignKey("alert_rules.id"), nullable=False), sa.Column("symbol", sa.String(16), nullable=False), sa.Column("dedupe_key", sa.String(128), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="OPEN"), sa.Column("message", sa.String(1024), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("rule_id", "symbol", "dedupe_key", name="uq_alert_dedupe")); op.create_index("ix_alerts_rule_id", "alerts", ["rule_id"]); op.create_index("ix_alerts_symbol", "alerts", ["symbol"])

def downgrade():
    op.drop_table("alerts"); op.drop_table("alert_rules"); op.drop_table("watchlist_items"); op.drop_table("watchlists"); op.drop_table("job_runs"); op.drop_table("jobs")

"""add production scheduler metadata and idempotency key"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("scope", sa.String(64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_freshness", sa.String(32), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
    ]
    for column in columns:
        op.add_column("jobs", column)
    op.create_index("ix_jobs_provider", "jobs", ["provider"])
    op.create_index("ix_jobs_scope", "jobs", ["scope"])
    op.create_index("ix_jobs_error_code", "jobs", ["error_code"])
    op.create_index("ix_jobs_idempotency_key", "jobs", ["idempotency_key"], unique=True)


def downgrade():
    op.drop_index("ix_jobs_idempotency_key", table_name="jobs")
    op.drop_index("ix_jobs_error_code", table_name="jobs")
    op.drop_index("ix_jobs_scope", table_name="jobs")
    op.drop_index("ix_jobs_provider", table_name="jobs")
    for name in (
        "idempotency_key", "source_freshness", "cursor_to", "cursor_from",
        "error_count", "skipped_count", "updated_count", "inserted_count",
        "error_code", "finished_at", "started_at", "requested_at", "scope", "provider",
    ):
        op.drop_column("jobs", name)

"""add tokenized ownership and leases to automation jobs"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("claim_token", sa.String(64)))
        batch.add_column(sa.Column("run_id", sa.String(64)))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("worker_id", sa.String(128)))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.create_index("ix_jobs_claim_token", ["claim_token"])
        batch.create_index("ix_jobs_run_id", ["run_id"])
        batch.create_index("ix_jobs_lease_expires_at", ["lease_expires_at"])
    with op.batch_alter_table("job_runs") as batch:
        batch.add_column(sa.Column("run_id", sa.String(64)))
        batch.add_column(sa.Column("claim_token", sa.String(64)))
        batch.add_column(sa.Column("worker_id", sa.String(128)))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.create_index("ix_job_runs_run_id", ["run_id"], unique=True)
        batch.create_index("ix_job_runs_claim_token", ["claim_token"])


def downgrade():
    with op.batch_alter_table("job_runs") as batch:
        batch.drop_index("ix_job_runs_claim_token")
        batch.drop_index("ix_job_runs_run_id")
        batch.drop_column("lease_expires_at")
        batch.drop_column("heartbeat_at")
        batch.drop_column("worker_id")
        batch.drop_column("claim_token")
        batch.drop_column("run_id")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_index("ix_jobs_lease_expires_at")
        batch.drop_index("ix_jobs_run_id")
        batch.drop_index("ix_jobs_claim_token")
        batch.drop_column("heartbeat_at")
        batch.drop_column("worker_id")
        batch.drop_column("lease_expires_at")
        batch.drop_column("claimed_at")
        batch.drop_column("run_id")
        batch.drop_column("claim_token")

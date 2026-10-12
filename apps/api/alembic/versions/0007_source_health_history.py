"""track source success and failure timestamps"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("source_health", sa.Column("last_success_at", sa.DateTime(timezone=True)))
    op.add_column("source_health", sa.Column("last_failure_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("source_health", "last_failure_at")
    op.drop_column("source_health", "last_success_at")

"""persist structured financial validation issues"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("financial_validation_reports") as batch:
        batch.add_column(sa.Column("issues_json", sa.Text(), nullable=False, server_default="[]"))


def downgrade():
    with op.batch_alter_table("financial_validation_reports") as batch:
        batch.drop_column("issues_json")

"""persist price-series quality flags"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("price_observations") as batch:
        batch.add_column(
            sa.Column(
                "quality_flags_json", sa.Text(), nullable=False, server_default="[]"
            )
        )


def downgrade():
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_column("quality_flags_json")

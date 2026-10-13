"""add canonical financial metadata and versioned item mapping"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("financial_periods") as batch:
        batch.add_column(sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("accounting_standard", sa.String(32), nullable=False, server_default="unknown")
        )
        batch.add_column(sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("data_version", sa.String(32), nullable=False, server_default="financial-v1")
        )
        batch.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
        batch.create_index("ix_financial_periods_period_start", ["period_start"])
        batch.create_index("ix_financial_periods_retrieved_at", ["retrieved_at"])
        batch.create_index("ix_financial_periods_content_hash", ["content_hash"])

    op.execute(
        sa.text(
            "UPDATE financial_periods SET retrieved_at = updated_at "
            "WHERE retrieved_at IS NULL"
        )
    )
    with op.batch_alter_table("financial_periods") as batch:
        batch.alter_column("retrieved_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    with op.batch_alter_table("financial_statement_items") as batch:
        batch.add_column(sa.Column("raw_item_code", sa.String(128), nullable=True))
        batch.add_column(
            sa.Column("mapping_version", sa.String(32), nullable=False, server_default="financial-map-v1")
        )
        batch.create_index("ix_financial_statement_items_mapping_version", ["mapping_version"])

    op.execute(
        sa.text(
            "UPDATE financial_statement_items SET raw_item_code = item_code "
            "WHERE raw_item_code IS NULL"
        )
    )


def downgrade():
    with op.batch_alter_table("financial_statement_items") as batch:
        batch.drop_index("ix_financial_statement_items_mapping_version")
        batch.drop_column("mapping_version")
        batch.drop_column("raw_item_code")
    with op.batch_alter_table("financial_periods") as batch:
        batch.drop_index("ix_financial_periods_content_hash")
        batch.drop_index("ix_financial_periods_retrieved_at")
        batch.drop_index("ix_financial_periods_period_start")
        batch.drop_column("content_hash")
        batch.drop_column("data_version")
        batch.drop_column("validated_at")
        batch.drop_column("retrieved_at")
        batch.drop_column("accounting_standard")
        batch.drop_column("period_start")

"""add financial statement scope and amendment status"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s_%(column_2_name)s"
}


def upgrade():
    with op.batch_alter_table(
        "financial_periods", recreate="always", naming_convention=NAMING_CONVENTION
    ) as batch:
        batch.add_column(
            sa.Column(
                "statement_scope",
                sa.String(24),
                nullable=False,
                server_default="consolidated",
            )
        )
        batch.add_column(
            sa.Column(
                "statement_status",
                sa.String(24),
                nullable=False,
                server_default="original",
            )
        )
        batch.drop_constraint(
            "uq_financial_periods_security_id_period_end_period_type", type_="unique"
        )
        batch.create_unique_constraint(
            "uq_financial_period_scope",
            ["security_id", "period_end", "period_type", "statement_scope"],
        )


def downgrade():
    with op.batch_alter_table(
        "financial_periods", recreate="always", naming_convention=NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("uq_financial_period_scope", type_="unique")
        batch.create_unique_constraint(
            "uq_financial_periods_security_id_period_end_period_type",
            ["security_id", "period_end", "period_type"],
        )
        batch.drop_column("statement_status")
        batch.drop_column("statement_scope")

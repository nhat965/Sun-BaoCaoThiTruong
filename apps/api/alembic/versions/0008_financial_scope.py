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
    # The original 0004 constraint was unnamed. PostgreSQL assigns its own
    # identifier, while SQLite batch mode synthesizes a name from the naming
    # convention. Resolve the actual identifier before replacing the constraint.
    unique_constraints = sa.inspect(op.get_bind()).get_unique_constraints("financial_periods")
    matching = [
        constraint
        for constraint in unique_constraints
        if set(constraint["column_names"]) == {"security_id", "period_end", "period_type"}
        and len(constraint["column_names"]) == 3
    ]
    if len(matching) != 1:
        raise RuntimeError(
            "Expected exactly one legacy financial_periods unique constraint; "
            f"found {len(matching)}"
        )
    legacy_name = matching[0]["name"] or (
        "uq_financial_periods_security_id_period_end_period_type"
    )
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
        batch.drop_constraint(legacy_name, type_="unique")
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

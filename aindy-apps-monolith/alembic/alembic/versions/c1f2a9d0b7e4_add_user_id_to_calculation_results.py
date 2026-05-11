"""add_user_id_to_calculation_results

Revision ID: c1f2a9d0b7e4
Revises: a2ec23964f2c
Create Date: 2026-03-20 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1f2a9d0b7e4"
down_revision: Union[str, None] = "a2ec23964f2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "calculation_results" not in table_names:
        op.create_table(
            "calculation_results",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("metric_name", sa.String(), index=True),
            sa.Column("result_value", sa.Float()),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
    else:
        column_names = {c["name"] for c in inspector.get_columns("calculation_results")}
        if "user_id" not in column_names:
            op.add_column(
                "calculation_results",
                sa.Column("user_id", sa.String(), nullable=True),
            )

    index_names = {idx["name"] for idx in inspector.get_indexes("calculation_results")}
    if "ix_calculation_results_user_id" not in index_names:
        op.create_index(
            "ix_calculation_results_user_id",
            "calculation_results",
            ["user_id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "calculation_results" not in table_names:
        return

    index_names = {idx["name"] for idx in inspector.get_indexes("calculation_results")}
    if "ix_calculation_results_user_id" in index_names:
        op.drop_index("ix_calculation_results_user_id", table_name="calculation_results")

    column_names = {c["name"] for c in inspector.get_columns("calculation_results")}
    if "user_id" in column_names:
        op.drop_column("calculation_results", "user_id")

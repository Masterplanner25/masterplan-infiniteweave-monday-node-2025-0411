"""add_flow_run_dead_letter_fields

Revision ID: 3c5d7e9f1a2b
Revises: 2d4f6a8b0c1d
Create Date: 2026-04-26 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3c5d7e9f1a2b"
down_revision: Union[str, None] = "2d4f6a8b0c1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flow_runs",
        sa.Column("dead_letter_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "flow_runs",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("flow_runs", "dead_lettered_at")
    op.drop_column("flow_runs", "dead_letter_reason")

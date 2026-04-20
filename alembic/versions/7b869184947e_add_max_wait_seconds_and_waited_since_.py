"""add max_wait_seconds and waited_since to waiting_flow_run

Revision ID: 7b869184947e
Revises: c5d6e7f8a9b0
Create Date: 2026-04-19 17:47:23.034595

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b869184947e'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "waiting_flow_runs",
        sa.Column("max_wait_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "waiting_flow_runs",
        sa.Column(
            "waited_since",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("waiting_flow_runs", "waited_since")
    op.drop_column("waiting_flow_runs", "max_wait_seconds")

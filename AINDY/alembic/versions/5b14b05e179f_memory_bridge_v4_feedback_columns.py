"""memory_bridge_v4_feedback_columns

Revision ID: 5b14b05e179f
Revises: edc8c8d84cbb
Create Date: 2026-03-18 19:13:37.336160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b14b05e179f'
down_revision: Union[str, None] = 'edc8c8d84cbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Feedback signals
    op.add_column(
        "memory_nodes",
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("last_outcome", sa.String(), nullable=True),
    )
    # Values: "success" | "failure" | "neutral"

    op.add_column(
        "memory_nodes",
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
    )
    # Adaptive weight — starts at 1.0
    # Increases with successes, decreases with failures
    # Used in resonance v2 scoring


def downgrade() -> None:
    """Downgrade schema."""
    for col in [
        "success_count",
        "failure_count",
        "usage_count",
        "last_used_at",
        "last_outcome",
        "weight",
    ]:
        op.drop_column("memory_nodes", col)

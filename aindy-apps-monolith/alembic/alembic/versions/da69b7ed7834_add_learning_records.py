"""Add learning records

Revision ID: da69b7ed7834
Revises: 0f283bba22b9
Create Date: 2026-03-24 00:41:14.928574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'da69b7ed7834'
down_revision: Union[str, None] = '0f283bba22b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "learning_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("drop_point_id", sa.String(), nullable=True),
        sa.Column("prediction", sa.String(), nullable=True),
        sa.Column("predicted_at", sa.DateTime(), nullable=True),
        sa.Column("actual_outcome", sa.String(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("velocity_at_prediction", sa.Float(), nullable=True),
        sa.Column("narrative_at_prediction", sa.Float(), nullable=True),
        sa.Column("was_correct", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_learning_records_drop_point_id"),
        "learning_records",
        ["drop_point_id"],
        unique=False,
    )
    op.create_table(
        "learning_thresholds",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("velocity_trend", sa.Float(), nullable=False),
        sa.Column("narrative_trend", sa.Float(), nullable=False),
        sa.Column("early_velocity_rate", sa.Float(), nullable=False),
        sa.Column("early_narrative_ceiling", sa.Float(), nullable=False),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_learning_records_drop_point_id"), table_name="learning_records")
    op.drop_table("learning_records")
    op.drop_table("learning_thresholds")

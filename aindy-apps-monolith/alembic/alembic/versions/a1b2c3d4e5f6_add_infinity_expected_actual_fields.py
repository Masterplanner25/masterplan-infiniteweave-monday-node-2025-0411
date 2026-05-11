"""add infinity expected vs actual fields

Revision ID: a2b3c4d5e6f7
Revises: f0a1b2c3d4e5
Create Date: 2025-04-13 04:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loop_adjustments", sa.Column("expected_outcome", sa.String(), nullable=True))
    op.add_column("loop_adjustments", sa.Column("expected_score", sa.Integer(), nullable=True))
    op.add_column("loop_adjustments", sa.Column("actual_outcome", sa.String(), nullable=True))
    op.add_column("loop_adjustments", sa.Column("actual_score", sa.Integer(), nullable=True))
    op.add_column("loop_adjustments", sa.Column("prediction_accuracy", sa.Integer(), nullable=True))
    op.add_column("loop_adjustments", sa.Column("deviation_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("loop_adjustments", "deviation_score")
    op.drop_column("loop_adjustments", "prediction_accuracy")
    op.drop_column("loop_adjustments", "actual_score")
    op.drop_column("loop_adjustments", "actual_outcome")
    op.drop_column("loop_adjustments", "expected_score")
    op.drop_column("loop_adjustments", "expected_outcome")

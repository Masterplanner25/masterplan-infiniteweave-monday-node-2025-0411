"""infinity_algorithm_score_tables

Revision ID: 0d73b27b8470
Revises: baed57014d3d
Create Date: 2026-03-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d73b27b8470'
down_revision: Union[str, None] = 'baed57014d3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── user_scores (latest cached score per user) ──────────────────────────
    op.create_table(
        "user_scores",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("master_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("execution_speed_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("decision_efficiency_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("ai_productivity_boost_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("focus_quality_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("masterplan_progress_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("score_version", sa.String(), nullable=False, server_default="v1"),
        sa.Column("data_points_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.String(), nullable=True),
        sa.Column("trigger_event", sa.String(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_scores_user_id", "user_scores", ["user_id"], unique=True)

    # ── score_history (append-only time series) ─────────────────────────────
    op.create_table(
        "score_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("master_score", sa.Float(), nullable=False),
        sa.Column("execution_speed_score", sa.Float(), nullable=False),
        sa.Column("decision_efficiency_score", sa.Float(), nullable=False),
        sa.Column("ai_productivity_boost_score", sa.Float(), nullable=False),
        sa.Column("focus_quality_score", sa.Float(), nullable=False),
        sa.Column("masterplan_progress_score", sa.Float(), nullable=False),
        sa.Column("trigger_event", sa.String(), nullable=True),
        sa.Column("score_delta", sa.Float(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_score_history_user_id", "score_history", ["user_id"])
    op.create_index(
        "ix_score_history_user_calculated",
        "score_history",
        ["user_id", "calculated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_score_history_user_calculated")
    op.drop_index("ix_score_history_user_id")
    op.drop_table("score_history")
    op.drop_index("ix_user_scores_user_id")
    op.drop_table("user_scores")

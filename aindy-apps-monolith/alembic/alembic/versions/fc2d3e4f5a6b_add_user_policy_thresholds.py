"""add_user_policy_thresholds

Revision ID: fc2d3e4f5a6b
Revises: fb1c2d3e4f5a
Create Date: 2026-04-24 15:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "fc2d3e4f5a6b"
down_revision: Union[str, None] = "fb1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_policy_thresholds",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("execution_speed_low_threshold", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("decision_efficiency_low_threshold", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("ai_productivity_boost_low_threshold", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("focus_quality_low_threshold", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("masterplan_progress_low_threshold", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("offset_continue_highest_priority_task", sa.Float(), nullable=False, server_default="3.0"),
        sa.Column("offset_create_new_task", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("offset_reprioritize_tasks", sa.Float(), nullable=False, server_default="1.5"),
        sa.Column("offset_review_plan", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("adapted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_adapted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_policy_thresholds_user_id"),
        "user_policy_thresholds",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_policy_thresholds_user_id"), table_name="user_policy_thresholds")
    op.drop_table("user_policy_thresholds")

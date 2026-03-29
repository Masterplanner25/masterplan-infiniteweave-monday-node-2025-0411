"""add goals tables

Revision ID: d0e1f2a3b4c5
Revises: c9e0f1a2b3c4
Create Date: 2025-04-13 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d0e1f2a3b4c5"
down_revision = "c9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("goal_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("success_metric", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"], unique=False)
    op.create_index("ix_goals_name", "goals", ["name"], unique=False)
    op.create_index("ix_goals_goal_type", "goals", ["goal_type"], unique=False)
    op.create_index("ix_goals_status", "goals", ["status"], unique=False)

    op.create_table(
        "goal_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_update", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recent_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("success_signal", sa.Float(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goal_id"),
    )
    op.create_index("ix_goal_states_goal_id", "goal_states", ["goal_id"], unique=True)
    op.create_index("ix_goal_states_last_update", "goal_states", ["last_update"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_goal_states_last_update", table_name="goal_states")
    op.drop_index("ix_goal_states_goal_id", table_name="goal_states")
    op.drop_table("goal_states")
    op.drop_index("ix_goals_status", table_name="goals")
    op.drop_index("ix_goals_goal_type", table_name="goals")
    op.drop_index("ix_goals_name", table_name="goals")
    op.drop_index("ix_goals_user_id", table_name="goals")
    op.drop_table("goals")

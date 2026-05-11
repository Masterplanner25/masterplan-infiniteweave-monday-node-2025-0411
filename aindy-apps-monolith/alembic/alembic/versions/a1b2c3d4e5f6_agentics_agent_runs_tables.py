"""agentics_agent_runs_tables

Revision ID: a1b2c3d4e5f6
Revises: 0d73b27b8470
Create Date: 2026-03-24

Creates agent_runs, agent_steps, agent_trust_settings tables for
Agentics Phase 1+2 (Sprint N+4 "First Agent").
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0d73b27b8470"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # agent_runs
    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("goal", sa.Text, nullable=False),
        sa.Column("plan", JSONB, nullable=True),
        sa.Column("executive_summary", sa.Text, nullable=True),
        sa.Column("overall_risk", sa.String(16), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
        sa.Column("steps_total", sa.Integer, server_default="0"),
        sa.Column("steps_completed", sa.Integer, server_default="0"),
        sa.Column("current_step", sa.Integer, server_default="0"),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_user_status", "agent_runs", ["user_id", "status"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])

    # agent_steps
    op.create_table(
        "agent_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tool_args", JSONB, nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("execution_ms", sa.Integer, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])

    # agent_trust_settings
    op.create_table(
        "agent_trust_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("auto_execute_low", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("auto_execute_medium", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_agent_trust_settings_user_id",
        "agent_trust_settings",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("agent_trust_settings")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")

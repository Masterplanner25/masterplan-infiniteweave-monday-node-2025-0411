"""flow_engine_phase_b_tables

Creates the 4 tables required by Flow Engine Phase B:
  flow_runs       — persistent execution state, WAIT/RESUME tracking
  flow_history    — per-node audit trail
  event_outcomes  — success/failure tracking for strategy learning
  strategies      — learned flow selection with adaptive scoring

Revision ID: b5d4e3f2c1a0
Revises: a4c9e2f1b8d3
Create Date: 2026-03-22 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d4e3f2c1a0'
down_revision: Union[str, None] = 'a4c9e2f1b8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── flow_runs ──────────────────────────────────────────────────────────────
    op.create_table(
        "flow_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("flow_name", sa.String(), nullable=False, index=True),
        sa.Column("workflow_type", sa.String(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("current_node", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("waiting_for", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True, index=True),
        sa.Column(
            "automation_log_id",
            sa.String(),
            sa.ForeignKey("automation_logs.id"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_flow_runs_status", "flow_runs", ["status"])
    op.create_index("ix_flow_runs_waiting_for", "flow_runs", ["waiting_for"])

    # ── flow_history ───────────────────────────────────────────────────────────
    op.create_table(
        "flow_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "flow_run_id",
            sa.String(),
            sa.ForeignKey("flow_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("node_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_state", sa.JSON(), nullable=True),
        sa.Column("output_patch", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── event_outcomes ─────────────────────────────────────────────────────────
    op.create_table(
        "event_outcomes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False, index=True),
        sa.Column("flow_name", sa.String(), nullable=False),
        sa.Column("workflow_type", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True, index=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── strategies ─────────────────────────────────────────────────────────────
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("intent_type", sa.String(), nullable=False, index=True),
        sa.Column("flow", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("strategies")
    op.drop_table("event_outcomes")
    op.drop_table("flow_history")
    op.drop_table("flow_runs")

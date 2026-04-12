"""agent_events table and correlation_id columns — Sprint N+8

Revision ID: c9d8e7f6a5b4
Revises: d3e4f5a6b7c8
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9d8e7f6a5b4"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    # ── agent_events table ────────────────────────────────────────────────────
    op.create_table(
        "agent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=72), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_events_run_id", "agent_events", ["run_id"])
    op.create_index("ix_agent_events_user_id", "agent_events", ["user_id"])
    op.create_index("ix_agent_events_event_type", "agent_events", ["event_type"])
    op.create_index("ix_agent_events_correlation_id", "agent_events", ["correlation_id"])
    op.create_index(
        "ix_agent_events_run_id_occurred_at",
        "agent_events",
        ["run_id", "occurred_at"],
    )
    op.create_index(
        "ix_agent_events_user_id_occurred_at",
        "agent_events",
        ["user_id", "occurred_at"],
    )

    # ── correlation_id on agent_runs ──────────────────────────────────────────
    op.add_column(
        "agent_runs",
        sa.Column("correlation_id", sa.String(length=72), nullable=True),
    )
    op.create_index("ix_agent_runs_correlation_id", "agent_runs", ["correlation_id"])

    # ── correlation_id on agent_steps ─────────────────────────────────────────
    op.add_column(
        "agent_steps",
        sa.Column("correlation_id", sa.String(length=72), nullable=True),
    )
    op.create_index("ix_agent_steps_correlation_id", "agent_steps", ["correlation_id"])


def downgrade():
    op.drop_index("ix_agent_steps_correlation_id", table_name="agent_steps")
    op.drop_column("agent_steps", "correlation_id")

    op.drop_index("ix_agent_runs_correlation_id", table_name="agent_runs")
    op.drop_column("agent_runs", "correlation_id")

    op.drop_index("ix_agent_events_user_id_occurred_at", table_name="agent_events")
    op.drop_index("ix_agent_events_run_id_occurred_at", table_name="agent_events")
    op.drop_index("ix_agent_events_correlation_id", table_name="agent_events")
    op.drop_index("ix_agent_events_event_type", table_name="agent_events")
    op.drop_index("ix_agent_events_user_id", table_name="agent_events")
    op.drop_index("ix_agent_events_run_id", table_name="agent_events")
    op.drop_table("agent_events")

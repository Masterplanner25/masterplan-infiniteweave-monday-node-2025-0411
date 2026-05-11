"""add system state snapshots

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-03-28 21:25:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_state_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("active_runs", sa.Integer(), nullable=False),
        sa.Column("failure_rate", sa.Float(), nullable=False),
        sa.Column("avg_execution_time", sa.Float(), nullable=False),
        sa.Column("recent_event_count", sa.Integer(), nullable=False),
        sa.Column("system_load", sa.Float(), nullable=False),
        sa.Column("dominant_event_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("health_status", sa.String(length=32), nullable=False),
        sa.Column("repeated_failures", sa.Integer(), nullable=False),
        sa.Column("spike_detected", sa.Integer(), nullable=False),
        sa.Column("unusual_patterns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_state_snapshots_id", "system_state_snapshots", ["id"], unique=False)
    op.create_index("ix_system_state_snapshots_created_at", "system_state_snapshots", ["created_at"], unique=False)
    op.create_index("ix_system_state_snapshots_health_status", "system_state_snapshots", ["health_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_state_snapshots_health_status", table_name="system_state_snapshots")
    op.drop_index("ix_system_state_snapshots_created_at", table_name="system_state_snapshots")
    op.drop_index("ix_system_state_snapshots_id", table_name="system_state_snapshots")
    op.drop_table("system_state_snapshots")

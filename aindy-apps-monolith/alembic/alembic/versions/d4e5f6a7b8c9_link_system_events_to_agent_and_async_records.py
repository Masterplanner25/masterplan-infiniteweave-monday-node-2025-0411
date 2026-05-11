"""link system events to agent and async records

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-26 10:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_logs",
        sa.Column("trace_id", sa.String(), nullable=True),
    )
    op.create_index("ix_automation_logs_trace_id", "automation_logs", ["trace_id"], unique=False)
    op.execute("UPDATE automation_logs SET trace_id = id WHERE trace_id IS NULL")

    op.add_column(
        "agent_events",
        sa.Column("system_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_agent_events_system_event_id", "agent_events", ["system_event_id"], unique=False)
    op.create_foreign_key(
        "fk_agent_events_system_event_id",
        "agent_events",
        "system_events",
        ["system_event_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_events_system_event_id", "agent_events", type_="foreignkey")
    op.drop_index("ix_agent_events_system_event_id", table_name="agent_events")
    op.drop_column("agent_events", "system_event_id")

    op.drop_index("ix_automation_logs_trace_id", table_name="automation_logs")
    op.drop_column("automation_logs", "trace_id")

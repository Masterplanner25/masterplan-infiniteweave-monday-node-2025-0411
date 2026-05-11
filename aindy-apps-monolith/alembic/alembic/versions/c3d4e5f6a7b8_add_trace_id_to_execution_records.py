"""add trace_id to execution records

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-25 21:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("request_metrics", sa.Column("trace_id", sa.String(), nullable=True))
    op.create_index("ix_request_metrics_trace_id", "request_metrics", ["trace_id"], unique=False)

    op.add_column("flow_runs", sa.Column("trace_id", sa.String(), nullable=True))
    op.create_index("ix_flow_runs_trace_id", "flow_runs", ["trace_id"], unique=False)

    op.add_column("loop_adjustments", sa.Column("trace_id", sa.String(), nullable=True))
    op.create_index("ix_loop_adjustments_trace_id", "loop_adjustments", ["trace_id"], unique=False)

    op.add_column("agent_runs", sa.Column("trace_id", sa.String(length=128), nullable=True))
    op.create_index("ix_agent_runs_trace_id", "agent_runs", ["trace_id"], unique=False)

    op.execute("UPDATE request_metrics SET trace_id = request_id WHERE trace_id IS NULL")
    op.execute(
        """
        UPDATE flow_runs
        SET trace_id = COALESCE(state ->> 'trace_id', id)
        WHERE trace_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE loop_adjustments
        SET trace_id = 'loop:' || id::text
        WHERE trace_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE agent_runs
        SET trace_id = COALESCE(correlation_id, id::text)
        WHERE trace_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_trace_id", table_name="agent_runs")
    op.drop_column("agent_runs", "trace_id")

    op.drop_index("ix_loop_adjustments_trace_id", table_name="loop_adjustments")
    op.drop_column("loop_adjustments", "trace_id")

    op.drop_index("ix_flow_runs_trace_id", table_name="flow_runs")
    op.drop_column("flow_runs", "trace_id")

    op.drop_index("ix_request_metrics_trace_id", table_name="request_metrics")
    op.drop_column("request_metrics", "trace_id")

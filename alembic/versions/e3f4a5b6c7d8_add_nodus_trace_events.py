"""add_nodus_trace_events

Adds nodus_trace_events table for GET /platform/nodus/trace/{trace_id}.

Each row captures one host-function call made during a Nodus script run
(recall, remember, emit, set_state, etc.).  Written in bulk after each
execution by nodus_runtime_adapter._flush_nodus_traces().

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodus_trace_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_unit_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fn_name", sa.String(64), nullable=False),
        sa.Column("args_summary", JSON(), nullable=True),
        sa.Column("result_summary", JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_nodus_trace_events_execution_unit_id",
        "nodus_trace_events",
        ["execution_unit_id"],
    )
    op.create_index(
        "ix_nodus_trace_events_trace_id",
        "nodus_trace_events",
        ["trace_id"],
    )
    op.create_index(
        "ix_nodus_trace_events_user_id",
        "nodus_trace_events",
        ["user_id"],
    )
    op.create_index(
        "ix_nodus_trace_events_timestamp",
        "nodus_trace_events",
        ["timestamp"],
    )
    # Composite index for the primary query pattern: trace_id + sequence ORDER BY
    op.create_index(
        "ix_nodus_trace_events_trace_id_sequence",
        "nodus_trace_events",
        ["trace_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_nodus_trace_events_trace_id_sequence", table_name="nodus_trace_events")
    op.drop_index("ix_nodus_trace_events_timestamp", table_name="nodus_trace_events")
    op.drop_index("ix_nodus_trace_events_user_id", table_name="nodus_trace_events")
    op.drop_index("ix_nodus_trace_events_trace_id", table_name="nodus_trace_events")
    op.drop_index("ix_nodus_trace_events_execution_unit_id", table_name="nodus_trace_events")
    op.drop_table("nodus_trace_events")

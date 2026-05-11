"""create system events table

Revision ID: a1b2c3d4e5f7
Revises: f7a8b9c0d1e2
Create Date: 2026-03-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_events_type"), "system_events", ["type"], unique=False)
    op.create_index(op.f("ix_system_events_user_id"), "system_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_system_events_trace_id"), "system_events", ["trace_id"], unique=False)
    op.create_index(op.f("ix_system_events_timestamp"), "system_events", ["timestamp"], unique=False)
    op.create_index(
        "ix_system_events_user_id_timestamp",
        "system_events",
        ["user_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_system_events_trace_id_timestamp",
        "system_events",
        ["trace_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_system_events_trace_id_timestamp", table_name="system_events")
    op.drop_index("ix_system_events_user_id_timestamp", table_name="system_events")
    op.drop_index(op.f("ix_system_events_timestamp"), table_name="system_events")
    op.drop_index(op.f("ix_system_events_trace_id"), table_name="system_events")
    op.drop_index(op.f("ix_system_events_user_id"), table_name="system_events")
    op.drop_index(op.f("ix_system_events_type"), table_name="system_events")
    op.drop_table("system_events")

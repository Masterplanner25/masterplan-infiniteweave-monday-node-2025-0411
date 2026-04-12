"""add parent and source to system events

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-26 11:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_events",
        sa.Column("parent_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "system_events",
        sa.Column("source", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_system_events_parent_event_id", "system_events", ["parent_event_id"], unique=False)
    op.create_index("ix_system_events_source", "system_events", ["source"], unique=False)
    op.create_index(
        "ix_system_events_parent_event_id_timestamp",
        "system_events",
        ["parent_event_id", "timestamp"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_system_events_parent_event_id",
        "system_events",
        "system_events",
        ["parent_event_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_system_events_parent_event_id", "system_events", type_="foreignkey")
    op.drop_index("ix_system_events_parent_event_id_timestamp", table_name="system_events")
    op.drop_index("ix_system_events_source", table_name="system_events")
    op.drop_index("ix_system_events_parent_event_id", table_name="system_events")
    op.drop_column("system_events", "source")
    op.drop_column("system_events", "parent_event_id")

"""add_platform_event_edges

Revision ID: 4b7c8d9e0f11
Revises: 3f6a9b2c4d10
Create Date: 2026-04-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4b7c8d9e0f11"
down_revision: Union[str, Sequence[str], None] = "3f6a9b2c4d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("system_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("system_events.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_memory_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(target_event_id IS NOT NULL) <> (target_memory_node_id IS NOT NULL)",
            name="ck_event_edges_single_target",
        ),
    )
    op.create_index("ix_event_edges_source_event_id", "event_edges", ["source_event_id"])
    op.create_index("ix_event_edges_target_event_id", "event_edges", ["target_event_id"])
    op.create_index("ix_event_edges_target_memory_node_id", "event_edges", ["target_memory_node_id"])
    op.create_index("ix_event_edges_relationship_type", "event_edges", ["relationship_type"])
    op.create_index("ix_event_edges_source_target", "event_edges", ["source_event_id", "target_event_id"])


def downgrade() -> None:
    op.drop_index("ix_event_edges_source_target", table_name="event_edges")
    op.drop_index("ix_event_edges_relationship_type", table_name="event_edges")
    op.drop_index("ix_event_edges_target_memory_node_id", table_name="event_edges")
    op.drop_index("ix_event_edges_target_event_id", table_name="event_edges")
    op.drop_index("ix_event_edges_source_event_id", table_name="event_edges")
    op.drop_table("event_edges")

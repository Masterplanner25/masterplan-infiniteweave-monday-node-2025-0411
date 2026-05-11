"""create ripple edges table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-26 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ripple_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_event_id"], ["system_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_event_id"], ["system_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ripple_edges_source_event_id", "ripple_edges", ["source_event_id"], unique=False)
    op.create_index("ix_ripple_edges_target_event_id", "ripple_edges", ["target_event_id"], unique=False)
    op.create_index("ix_ripple_edges_relationship_type", "ripple_edges", ["relationship_type"], unique=False)
    op.create_index("ix_ripple_edges_source_target", "ripple_edges", ["source_event_id", "target_event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ripple_edges_source_target", table_name="ripple_edges")
    op.drop_index("ix_ripple_edges_relationship_type", table_name="ripple_edges")
    op.drop_index("ix_ripple_edges_target_event_id", table_name="ripple_edges")
    op.drop_index("ix_ripple_edges_source_event_id", table_name="ripple_edges")
    op.drop_table("ripple_edges")

"""memory_bridge_v3_history_table

Revision ID: dc59c589ab1e
Revises: d37ae6ebc319
Create Date: 2026-03-18 14:05:30.912789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dc59c589ab1e'
down_revision: Union[str, None] = 'd37ae6ebc319'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_node_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_nodes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.Column("previous_content", sa.Text(), nullable=True),
        sa.Column("previous_tags", sa.JSON(), nullable=True),
        sa.Column("previous_node_type", sa.String(), nullable=True),
        sa.Column("previous_source", sa.String(), nullable=True),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_memory_node_history_node_changed",
        "memory_node_history",
        ["node_id", "changed_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memory_node_history_node_changed")
    op.drop_table("memory_node_history")

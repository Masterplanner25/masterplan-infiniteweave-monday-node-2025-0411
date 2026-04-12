"""init memory persistence

Revision ID: c7602451aabb
Revises:
Create Date: 2025-10-12 18:30:30.229453
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7602451aabb"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create base memory tables."""
    op.create_table(
        "memory_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("node_type", sa.String(50), nullable=False, default="generic"),
        sa.Column("tags", postgresql.ARRAY(sa.String(50)), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "memory_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(50), nullable=False),
        sa.Column("strength", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["source_node_id"], ["memory_nodes.id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["memory_nodes.id"]),
    )


def downgrade() -> None:
    """Drop base memory tables."""
    op.drop_table("memory_links")
    op.drop_table("memory_nodes")


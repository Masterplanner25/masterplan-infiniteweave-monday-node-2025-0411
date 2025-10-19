"""create memory persistence tables (nodes + links)

Revision ID: 20251011_mem_persistence
Revises: <put_previous_revision_here>
Create Date: 2025-10-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251011_mem_persistence"
down_revision = "<put_previous_revision_here>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    # GIN index for JSONB tag queries
    op.create_index(
        "ix_memory_nodes_tags_gin",
        "memory_nodes",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "memory_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False),
        sa.Column("strength", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_memory_links_source", "memory_links", ["source_node_id"], unique=False)
    op.create_index("ix_memory_links_target", "memory_links", ["target_node_id"], unique=False)
    op.create_index(
        "uq_memory_links_unique",
        "memory_links",
        ["source_node_id", "target_node_id", "link_type"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_memory_links_unique", table_name="memory_links")
    op.drop_index("ix_memory_links_target", table_name="memory_links")
    op.drop_index("ix_memory_links_source", table_name="memory_links")
    op.drop_table("memory_links")

    op.drop_index("ix_memory_nodes_tags_gin", table_name="memory_nodes")
    op.drop_table("memory_nodes")

"""create memory nodes + links (indexes only)

Revision ID: bff24d352475
Revises: c7602451aabb
Create Date: 2025-10-12
"""
from alembic import op
from sqlalchemy import text

revision = "bff24d352475"
down_revision = "c7602451aabb"
branch_labels = None
depends_on = None


def upgrade():
    # Add useful indexes that weren't in the base migration
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_memory_nodes_tags_gin
        ON memory_nodes USING gin ((tags));
    """))

    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_links_unique
        ON memory_links (source_node_id, target_node_id, link_type);
    """))

    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_memory_links_source
        ON memory_links (source_node_id);
    """))

    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_memory_links_target
        ON memory_links (target_node_id);
    """))


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_tags_gin;")
    op.execute("DROP INDEX IF EXISTS uq_memory_links_unique;")
    op.execute("DROP INDEX IF EXISTS ix_memory_links_source;")
    op.execute("DROP INDEX IF EXISTS ix_memory_links_target;")

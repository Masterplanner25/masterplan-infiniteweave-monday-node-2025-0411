"""improve memory nodes indexes

Revision ID: 831b86c9e536
Revises: bff24d352475
Create Date: 2025-10-12 23:49:29.475030
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "831b86c9e536"
down_revision: Union[str, None] = "bff24d352475"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    conn = op.get_bind()

    # enable pgcrypto for gen_random_uuid
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

    # set default UUID on memory_nodes
    op.execute(text("""
        ALTER TABLE memory_nodes
        ALTER COLUMN id SET DEFAULT gen_random_uuid();
    """))

    # add indexes for faster search
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_memory_nodes_content_tsv
        ON memory_nodes USING gin (to_tsvector('english', content));
    """))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_nodes_node_type ON memory_nodes(node_type);"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_nodes_created_at ON memory_nodes(created_at);"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_links_source ON memory_links(source_node_id);"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_links_target ON memory_links(target_node_id);"))
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_memory_links_src_tgt_type
        ON memory_links(source_node_id, target_node_id, link_type);
    """))

    # trigger for automatic updated_at timestamp
    op.execute(text("""
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS trigger AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """))

    op.execute(text("""
    DROP TRIGGER IF EXISTS trg_update_memory_nodes_updated_at ON memory_nodes;
    CREATE TRIGGER trg_update_memory_nodes_updated_at
    BEFORE UPDATE ON memory_nodes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
    """))


def downgrade():
    op.execute(text("DROP INDEX IF EXISTS ix_memory_nodes_content_tsv;"))
    op.execute(text("DROP INDEX IF EXISTS ix_memory_nodes_node_type;"))
    op.execute(text("DROP INDEX IF EXISTS ix_memory_nodes_created_at;"))
    op.execute(text("DROP INDEX IF EXISTS ix_memory_links_source;"))
    op.execute(text("DROP INDEX IF EXISTS ix_memory_links_target;"))
    op.execute(text("DROP INDEX IF EXISTS ux_memory_links_src_tgt_type;"))
    op.execute(text("DROP TRIGGER IF EXISTS trg_update_memory_nodes_updated_at ON memory_nodes;"))
    op.execute(text("DROP FUNCTION IF EXISTS update_updated_at_column;"))

"""improve memory_nodes: uuid defaults, tsv, triggers, indexes

Revision ID: a318e9194478
Revises: 831b86c9e536
Create Date: 2025-10-12 23:50:17.040860

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'a318e9194478'
down_revision: Union[str, None] = '831b86c9e536'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    conn = op.get_bind()

    # 0) extension
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

    # 1) set uuid defaults
    op.execute("""
    ALTER TABLE memory_nodes
      ALTER COLUMN id SET DEFAULT gen_random_uuid();
    """)
    op.execute("""
    ALTER TABLE memory_links
      ALTER COLUMN id SET DEFAULT gen_random_uuid();
    """)

    # 2) updated_at function & trigger for memory_nodes
    op.execute("""
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS trigger AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_update_memory_nodes_updated_at ON memory_nodes;")
    op.execute("""
    CREATE TRIGGER trg_update_memory_nodes_updated_at
    BEFORE UPDATE ON memory_nodes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
    """)

    # 3) tsvector column + populate + index + trigger
    op.execute("ALTER TABLE memory_nodes ADD COLUMN IF NOT EXISTS content_tsv tsvector;")
    op.execute("UPDATE memory_nodes SET content_tsv = to_tsvector('english', coalesce(content,''));")
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_memory_nodes_content_tsv ON memory_nodes USING gin (content_tsv);
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION memory_nodes_tsv_trigger() RETURNS trigger AS $$
    BEGIN
      NEW.content_tsv := to_tsvector('english', coalesce(NEW.content,''));
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_memory_nodes_tsv ON memory_nodes;")
    op.execute("""
    CREATE TRIGGER trg_memory_nodes_tsv
    BEFORE INSERT OR UPDATE ON memory_nodes
    FOR EACH ROW EXECUTE FUNCTION memory_nodes_tsv_trigger();
    """)

    # 4) btree indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_memory_nodes_node_type ON memory_nodes(node_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_memory_nodes_created_at ON memory_nodes(created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_memory_links_source ON memory_links(source_node_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_memory_links_target ON memory_links(target_node_id);")
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_links_unique ON memory_links(source_node_id, target_node_id, link_type);
    """)


def downgrade():
    # keep downgrade conservative
    op.execute("DROP TRIGGER IF EXISTS trg_memory_nodes_tsv ON memory_nodes;")
    op.execute("DROP FUNCTION IF EXISTS memory_nodes_tsv_trigger();")
    op.execute("DROP TRIGGER IF EXISTS trg_update_memory_nodes_updated_at ON memory_nodes;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_content_tsv;")
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_node_type;")
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_memory_links_source;")
    op.execute("DROP INDEX IF EXISTS ix_memory_links_target;")
    # keep defaults as-is; removing defaults can be invasive and is avoided here
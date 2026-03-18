"""repair_memory_nodes_tsv_trigger_drift

Revision ID: edc8c8d84cbb
Revises: dc59c589ab1e
Create Date: 2026-03-18 14:39:26.123854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'edc8c8d84cbb'
down_revision: Union[str, None] = 'dc59c589ab1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_memory_nodes_tsv ON memory_nodes"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS memory_nodes_tsv_trigger()"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_memory_nodes_content_tsv"))
    op.execute(sa.text("ALTER TABLE memory_nodes DROP COLUMN IF EXISTS content_tsv"))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("ALTER TABLE memory_nodes ADD COLUMN IF NOT EXISTS content_tsv tsvector"))
    op.execute(
        sa.text(
            "UPDATE memory_nodes "
            "SET content_tsv = to_tsvector('english', coalesce(content, ''))"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_memory_nodes_content_tsv "
            "ON memory_nodes USING gin (content_tsv)"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION memory_nodes_tsv_trigger()
            RETURNS trigger AS $$
            BEGIN
              NEW.content_tsv := to_tsvector('english', coalesce(NEW.content, ''));
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_memory_nodes_tsv
            BEFORE INSERT OR UPDATE OF content ON memory_nodes
            FOR EACH ROW EXECUTE FUNCTION memory_nodes_tsv_trigger()
            """
        )
    )

"""add hnsw index for memory_nodes embedding

Revision ID: f3a4b5c6d7e8
Revises: e2c3d4f5a6b7
Create Date: 2026-03-21
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f3a4b5c6d7e8"
down_revision = "e2c3d4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memory_nodes_embedding_hnsw ON memory_nodes USING hnsw (embedding vector_cosine_ops);"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_embedding_hnsw;")

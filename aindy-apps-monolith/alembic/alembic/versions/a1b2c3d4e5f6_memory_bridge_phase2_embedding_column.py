"""memory_bridge_phase2_embedding_column

Revision ID: mb2embed0001
Revises: d1a2b3c4d5e6
Create Date: 2026-03-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = 'mb2embed0001'
down_revision: Union[str, None] = 'd1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Check if column already exists before adding
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='memory_nodes' AND column_name='embedding'"
    ))
    if result.fetchone() is None:
        op.add_column(
            "memory_nodes",
            sa.Column("embedding", Vector(1536), nullable=True)
        )


def downgrade() -> None:
    op.drop_column("memory_nodes", "embedding")

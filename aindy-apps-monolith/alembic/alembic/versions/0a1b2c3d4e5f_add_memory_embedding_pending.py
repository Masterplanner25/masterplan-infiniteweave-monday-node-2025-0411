"""add memory embedding pending flag

Revision ID: 0a1b2c3d4e5f
Revises: fe4f5a6b7c8d
Create Date: 2026-04-25 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, None] = "fe4f5a6b7c8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory_nodes",
        sa.Column("embedding_pending", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        "UPDATE memory_nodes "
        "SET embedding_pending = CASE "
        "WHEN embedding IS NOT NULL AND embedding_status = 'complete' THEN FALSE "
        "ELSE TRUE "
        "END"
    )
    op.create_index(
        "ix_memory_nodes_embedding_pending",
        "memory_nodes",
        ["embedding_pending"],
        unique=False,
    )
    op.alter_column("memory_nodes", "embedding_pending", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_memory_nodes_embedding_pending", table_name="memory_nodes")
    op.drop_column("memory_nodes", "embedding_pending")

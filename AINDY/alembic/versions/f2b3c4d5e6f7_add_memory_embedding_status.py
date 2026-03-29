"""add memory embedding status

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-29 13:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory_nodes",
        sa.Column("embedding_status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.execute(
        "UPDATE memory_nodes "
        "SET embedding_status = CASE "
        "WHEN embedding IS NOT NULL THEN 'complete' "
        "ELSE 'pending' "
        "END"
    )
    op.create_index("ix_memory_nodes_embedding_status", "memory_nodes", ["embedding_status"], unique=False)
    op.alter_column("memory_nodes", "embedding_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_memory_nodes_embedding_status", table_name="memory_nodes")
    op.drop_column("memory_nodes", "embedding_status")

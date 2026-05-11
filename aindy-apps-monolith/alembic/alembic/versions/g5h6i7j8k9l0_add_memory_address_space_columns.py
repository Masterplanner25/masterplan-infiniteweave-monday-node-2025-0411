"""add_memory_address_space_columns

Revision ID: g5h6i7j8k9l0
Revises: f4g5h6i7j8k9
Create Date: 2026-04-01 00:00:00.000000

Adds MAS path columns to memory_nodes:
  path        — full address /memory/{tenant}/{ns}/{type}/{id}
  namespace   — logical domain segment
  addr_type   — sub-category segment (named addr_type to avoid 'type' keyword)
  parent_path — parent address (one level up)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "g5h6i7j8k9l0"
down_revision = "f4g5h6i7j8k9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_nodes", sa.Column("path", sa.String(512), nullable=True))
    op.add_column("memory_nodes", sa.Column("namespace", sa.String(128), nullable=True))
    op.add_column("memory_nodes", sa.Column("addr_type", sa.String(128), nullable=True))
    op.add_column("memory_nodes", sa.Column("parent_path", sa.String(512), nullable=True))

    op.create_index("ix_memory_nodes_path", "memory_nodes", ["path"])
    op.create_index("ix_memory_nodes_namespace", "memory_nodes", ["namespace"])
    op.create_index("ix_memory_nodes_addr_type", "memory_nodes", ["addr_type"])
    op.create_index("ix_memory_nodes_parent_path", "memory_nodes", ["parent_path"])


def downgrade() -> None:
    op.drop_index("ix_memory_nodes_parent_path", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_addr_type", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_namespace", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_path", table_name="memory_nodes")

    op.drop_column("memory_nodes", "parent_path")
    op.drop_column("memory_nodes", "addr_type")
    op.drop_column("memory_nodes", "namespace")
    op.drop_column("memory_nodes", "path")

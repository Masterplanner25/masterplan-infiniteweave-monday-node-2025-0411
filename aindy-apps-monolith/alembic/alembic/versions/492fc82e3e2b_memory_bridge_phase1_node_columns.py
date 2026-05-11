"""memory_bridge_phase1_node_columns

Revision ID: 492fc82e3e2b
Revises: a1b2c3d4e5f0
Create Date: 2026-03-17 23:59:39.852506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql


# revision identifiers, used by Alembic.
revision: str = '492fc82e3e2b'
down_revision: Union[str, None] = 'a1b2c3d4e5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add source, user_id columns to memory_nodes (extra already present)."""
    op.add_column('memory_nodes', sa.Column('source', sa.String(255), nullable=True))
    op.add_column('memory_nodes', sa.Column('user_id', sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove source, user_id columns from memory_nodes."""
    op.drop_column('memory_nodes', 'user_id')
    op.drop_column('memory_nodes', 'source')

"""genesis_block1_missing_columns

Revision ID: a1b2c3d4e5f6
Revises: 37f972780d54
Create Date: 2026-03-17 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '37f972780d54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns for Genesis Block 1. ADDITIVE ONLY — no drops or alters."""
    # genesis_sessions — add synthesis_ready, draft_json, locked_at, user_id_str
    op.add_column('genesis_sessions', sa.Column('synthesis_ready', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('genesis_sessions', sa.Column('draft_json', sa.JSON(), nullable=True))
    op.add_column('genesis_sessions', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('genesis_sessions', sa.Column('user_id_str', sa.String(), nullable=True))

    # master_plans — add user_id (String UUID), status
    op.add_column('master_plans', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('master_plans', sa.Column('status', sa.String(), nullable=True, server_default=sa.text("'draft'")))


def downgrade() -> None:
    """Remove Genesis Block 1 columns."""
    op.drop_column('master_plans', 'status')
    op.drop_column('master_plans', 'user_id')
    op.drop_column('genesis_sessions', 'user_id_str')
    op.drop_column('genesis_sessions', 'locked_at')
    op.drop_column('genesis_sessions', 'draft_json')
    op.drop_column('genesis_sessions', 'synthesis_ready')

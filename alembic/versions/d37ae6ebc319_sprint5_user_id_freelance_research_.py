"""sprint5_user_id_freelance_research_rippletrace

Revision ID: d37ae6ebc319
Revises: mb2embed0001
Create Date: 2026-03-18 11:18:05.997633

Adds user_id (String, nullable, indexed) to:
  - freelance_orders
  - client_feedback
  - research_results
  - drop_points
  - pings
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd37ae6ebc319'
down_revision: Union[str, None] = 'mb2embed0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Freelance
    op.add_column('freelance_orders', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index('ix_freelance_orders_user_id', 'freelance_orders', ['user_id'])

    op.add_column('client_feedback', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index('ix_client_feedback_user_id', 'client_feedback', ['user_id'])

    # Research
    op.add_column('research_results', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index('ix_research_results_user_id', 'research_results', ['user_id'])

    # Rippletrace
    op.add_column('drop_points', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index('ix_drop_points_user_id', 'drop_points', ['user_id'])

    op.add_column('pings', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index('ix_pings_user_id', 'pings', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_pings_user_id', 'pings')
    op.drop_column('pings', 'user_id')

    op.drop_index('ix_drop_points_user_id', 'drop_points')
    op.drop_column('drop_points', 'user_id')

    op.drop_index('ix_research_results_user_id', 'research_results')
    op.drop_column('research_results', 'user_id')

    op.drop_index('ix_client_feedback_user_id', 'client_feedback')
    op.drop_column('client_feedback', 'user_id')

    op.drop_index('ix_freelance_orders_user_id', 'freelance_orders')
    op.drop_column('freelance_orders', 'user_id')

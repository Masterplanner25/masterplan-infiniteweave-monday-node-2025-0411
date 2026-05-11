"""merge heads

Revision ID: cc88b538c4a7
Revises: 7c12f8c9a1b4, c1f2a9d0b7e4
Create Date: 2026-03-21 19:25:45.159337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc88b538c4a7'
down_revision: Union[str, None] = ('7c12f8c9a1b4', 'c1f2a9d0b7e4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

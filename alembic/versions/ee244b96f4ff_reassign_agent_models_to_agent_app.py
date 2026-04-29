"""reassign agent models to agent app

Revision ID: ee244b96f4ff
Revises: 261f46c34f7c
Create Date: 2026-04-28 23:04:29.806481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee244b96f4ff'
down_revision: Union[str, None] = '261f46c34f7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

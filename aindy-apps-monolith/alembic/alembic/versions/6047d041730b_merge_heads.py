"""merge heads

Revision ID: 6047d041730b
Revises: a2b3c4d5e6f7, e2f3a4b5c6d7
Create Date: 2026-03-29 09:29:41.210703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6047d041730b'
down_revision: Union[str, None] = ('a2b3c4d5e6f7', 'e2f3a4b5c6d7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

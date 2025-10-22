"""merge heads from split history

Revision ID: 23e1012a48d5
Revises: 2a21184b206a, a318e9194478
Create Date: 2025-10-16 19:52:59.359355

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23e1012a48d5'
down_revision: Union[str, None] = ('2a21184b206a', 'a318e9194478')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

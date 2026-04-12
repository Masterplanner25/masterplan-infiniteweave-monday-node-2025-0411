"""merge heads after auth identity cleanup

Revision ID: 23da8ebc43f1
Revises: 3c1b2a4d5e6f, b7c8d9e0f1a2
Create Date: 2026-03-22 12:03:53.295914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23da8ebc43f1'
down_revision: Union[str, None] = ('3c1b2a4d5e6f', 'b7c8d9e0f1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

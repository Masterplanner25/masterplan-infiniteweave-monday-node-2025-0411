"""merge_heads_before_infinity_score

Revision ID: baed57014d3d
Revises: d7e6f5a4b3c2, f6c7d8a9b2e1
Create Date: 2026-03-24 19:03:54.903790

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'baed57014d3d'
down_revision: Union[str, None] = ('d7e6f5a4b3c2', 'f6c7d8a9b2e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

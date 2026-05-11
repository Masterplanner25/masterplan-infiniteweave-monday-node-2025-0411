"""merge_wait_condition_and_schema_drift

Revision ID: 2c6054da62a1
Revises: h1i2j3k4l5m6, ab83602dd6a9
Create Date: 2026-04-07 21:02:56.192814

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c6054da62a1'
down_revision: Union[str, None] = ('h1i2j3k4l5m6', 'ab83602dd6a9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

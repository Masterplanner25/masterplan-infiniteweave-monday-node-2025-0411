"""merge system event and loop heads

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7, f1e2d3c4b5a6
Create Date: 2026-03-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, tuple[str, str], None] = ("a1b2c3d4e5f7", "f1e2d3c4b5a6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

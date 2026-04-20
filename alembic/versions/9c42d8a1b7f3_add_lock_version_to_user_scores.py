"""add lock_version to user_scores

Revision ID: 9c42d8a1b7f3
Revises: 7b869184947e
Create Date: 2026-04-19 19:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c42d8a1b7f3"
down_revision: Union[str, None] = "7b869184947e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_scores",
        sa.Column(
            "lock_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_scores", "lock_version")

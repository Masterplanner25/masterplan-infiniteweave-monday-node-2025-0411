"""add_user_token_version

Revision ID: c2784a986e19
Revises: 4f9b7c2d1a6e
Create Date: 2026-04-23 18:39:42.714226

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2784a986e19"
down_revision: Union[str, None] = "4f9b7c2d1a6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")

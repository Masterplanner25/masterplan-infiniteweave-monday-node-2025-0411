"""Add playbooks table

Revision ID: f6c7d8a9b2e1
Revises: e350a1bb6696
Create Date: 2026-03-24 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6c7d8a9b2e1"
down_revision: Union[str, None] = "e350a1bb6696"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("strategy_id", sa.String(), nullable=True, index=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=True),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("playbooks")

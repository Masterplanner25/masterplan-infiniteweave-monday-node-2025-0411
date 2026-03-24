"""Recreate strategies table for Strategy Engine v1

Revision ID: e350a1bb6696
Revises: da69b7ed7834
Create Date: 2026-03-24 07:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "e350a1bb6696"
down_revision: Union[str, None] = "da69b7ed7834"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("strategies")
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("pattern_description", sa.Text(), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("success_rate", sa.Float(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("strategies")
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("intent_type", sa.String(), nullable=False, index=True),
        sa.Column("flow", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

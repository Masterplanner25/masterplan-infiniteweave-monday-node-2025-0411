"""add_freelance_refund_fields

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-04-24 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("freelance_orders", sa.Column("refund_id", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("refunded_at", sa.DateTime(), nullable=True))
    op.add_column("freelance_orders", sa.Column("refund_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("freelance_orders", "refund_reason")
    op.drop_column("freelance_orders", "refunded_at")
    op.drop_column("freelance_orders", "refund_id")

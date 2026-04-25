"""add_freelance_subscription_fields

Revision ID: fa0b1c2d3e4f
Revises: f9b0c1d2e3f4
Create Date: 2026-04-24 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fa0b1c2d3e4f"
down_revision: Union[str, None] = "f9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("freelance_orders", sa.Column("stripe_subscription_id", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("subscription_status", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("subscription_period_end", sa.DateTime(), nullable=True))
    op.create_index(
        op.f("ix_freelance_orders_stripe_subscription_id"),
        "freelance_orders",
        ["stripe_subscription_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_freelance_orders_stripe_subscription_id"), table_name="freelance_orders")
    op.drop_column("freelance_orders", "subscription_period_end")
    op.drop_column("freelance_orders", "subscription_status")
    op.drop_column("freelance_orders", "stripe_customer_id")
    op.drop_column("freelance_orders", "stripe_subscription_id")

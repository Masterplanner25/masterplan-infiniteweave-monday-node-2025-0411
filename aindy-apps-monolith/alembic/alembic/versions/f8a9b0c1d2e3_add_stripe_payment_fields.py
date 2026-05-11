"""add_stripe_payment_fields

Revision ID: f8a9b0c1d2e3
Revises: c2784a986e19
Create Date: 2026-04-24 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "c2784a986e19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("freelance_orders", sa.Column("stripe_payment_intent_id", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("stripe_payment_link_id", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("payment_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "freelance_orders",
        sa.Column("payment_status", sa.String(), nullable=True, server_default="none"),
    )
    op.create_index(
        op.f("ix_freelance_orders_stripe_payment_intent_id"),
        "freelance_orders",
        ["stripe_payment_intent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_freelance_orders_stripe_payment_link_id"),
        "freelance_orders",
        ["stripe_payment_link_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_freelance_orders_stripe_payment_link_id"), table_name="freelance_orders")
    op.drop_index(op.f("ix_freelance_orders_stripe_payment_intent_id"), table_name="freelance_orders")
    op.drop_column("freelance_orders", "payment_status")
    op.drop_column("freelance_orders", "payment_confirmed_at")
    op.drop_column("freelance_orders", "stripe_payment_link_id")
    op.drop_column("freelance_orders", "stripe_payment_intent_id")

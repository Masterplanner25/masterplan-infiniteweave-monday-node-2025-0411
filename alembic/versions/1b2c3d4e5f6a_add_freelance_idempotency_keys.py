"""add_freelance_idempotency_keys

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-04-25 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1b2c3d4e5f6a"
down_revision: Union[str, None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("freelance_orders", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_index(
        "ux_freelance_orders_idempotency_key",
        "freelance_orders",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "freelance_payment_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
        sa.Column("stripe_payment_link_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["freelance_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_freelance_payment_records_id"), "freelance_payment_records", ["id"], unique=False)
    op.create_index(op.f("ix_freelance_payment_records_order_id"), "freelance_payment_records", ["order_id"], unique=False)
    op.create_index(op.f("ix_freelance_payment_records_stripe_payment_intent_id"), "freelance_payment_records", ["stripe_payment_intent_id"], unique=False)
    op.create_index(op.f("ix_freelance_payment_records_stripe_payment_link_id"), "freelance_payment_records", ["stripe_payment_link_id"], unique=False)
    op.create_index(op.f("ix_freelance_payment_records_user_id"), "freelance_payment_records", ["user_id"], unique=False)
    op.create_index(
        "ux_freelance_payment_records_idempotency_key",
        "freelance_payment_records",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "freelance_refund_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
        sa.Column("stripe_refund_id", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["freelance_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_freelance_refund_records_id"), "freelance_refund_records", ["id"], unique=False)
    op.create_index(op.f("ix_freelance_refund_records_order_id"), "freelance_refund_records", ["order_id"], unique=False)
    op.create_index(op.f("ix_freelance_refund_records_stripe_payment_intent_id"), "freelance_refund_records", ["stripe_payment_intent_id"], unique=False)
    op.create_index(op.f("ix_freelance_refund_records_stripe_refund_id"), "freelance_refund_records", ["stripe_refund_id"], unique=False)
    op.create_index(op.f("ix_freelance_refund_records_user_id"), "freelance_refund_records", ["user_id"], unique=False)
    op.create_index(
        "ux_freelance_refund_records_idempotency_key",
        "freelance_refund_records",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "freelance_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("processing_status", sa.String(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_freelance_webhook_events_id"), "freelance_webhook_events", ["id"], unique=False)
    op.create_index(
        "ux_freelance_webhook_events_idempotency_key",
        "freelance_webhook_events",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_freelance_webhook_events_idempotency_key", table_name="freelance_webhook_events")
    op.drop_index(op.f("ix_freelance_webhook_events_id"), table_name="freelance_webhook_events")
    op.drop_table("freelance_webhook_events")

    op.drop_index("ux_freelance_refund_records_idempotency_key", table_name="freelance_refund_records")
    op.drop_index(op.f("ix_freelance_refund_records_user_id"), table_name="freelance_refund_records")
    op.drop_index(op.f("ix_freelance_refund_records_stripe_refund_id"), table_name="freelance_refund_records")
    op.drop_index(op.f("ix_freelance_refund_records_stripe_payment_intent_id"), table_name="freelance_refund_records")
    op.drop_index(op.f("ix_freelance_refund_records_order_id"), table_name="freelance_refund_records")
    op.drop_index(op.f("ix_freelance_refund_records_id"), table_name="freelance_refund_records")
    op.drop_table("freelance_refund_records")

    op.drop_index("ux_freelance_payment_records_idempotency_key", table_name="freelance_payment_records")
    op.drop_index(op.f("ix_freelance_payment_records_user_id"), table_name="freelance_payment_records")
    op.drop_index(op.f("ix_freelance_payment_records_stripe_payment_link_id"), table_name="freelance_payment_records")
    op.drop_index(op.f("ix_freelance_payment_records_stripe_payment_intent_id"), table_name="freelance_payment_records")
    op.drop_index(op.f("ix_freelance_payment_records_order_id"), table_name="freelance_payment_records")
    op.drop_index(op.f("ix_freelance_payment_records_id"), table_name="freelance_payment_records")
    op.drop_table("freelance_payment_records")

    op.drop_index("ux_freelance_orders_idempotency_key", table_name="freelance_orders")
    op.drop_column("freelance_orders", "idempotency_key")

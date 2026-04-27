"""add_stripe_webhook_event_claim_fields

Revision ID: 6b7c8d9e0f1a
Revises: 5e7f901b2c3d
Create Date: 2026-04-26 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b7c8d9e0f1a"
down_revision: Union[str, None] = "5e7f901b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "freelance_webhook_events",
        sa.Column("stripe_event_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "freelance_webhook_events",
        sa.Column("outcome", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "freelance_webhook_events",
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.execute(
        """
        UPDATE freelance_webhook_events
        SET stripe_event_id = idempotency_key
        WHERE stripe_event_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE freelance_webhook_events
        SET outcome = CASE
            WHEN processing_status = 'processed' THEN 'fulfilled'
            WHEN processing_status = 'ignored' THEN 'skipped'
            WHEN processing_status = 'failed' THEN 'failed'
            ELSE processing_status
        END
        WHERE outcome IS NULL
        """
    )
    op.create_index(
        op.f("ix_freelance_webhook_events_stripe_event_id"),
        "freelance_webhook_events",
        ["stripe_event_id"],
        unique=False,
    )
    op.create_index(
        "ux_freelance_webhook_events_stripe_event_id",
        "freelance_webhook_events",
        ["stripe_event_id"],
        unique=True,
        postgresql_where=sa.text("stripe_event_id IS NOT NULL"),
        sqlite_where=sa.text("stripe_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_freelance_webhook_events_stripe_event_id",
        table_name="freelance_webhook_events",
    )
    op.drop_index(
        op.f("ix_freelance_webhook_events_stripe_event_id"),
        table_name="freelance_webhook_events",
    )
    op.drop_column("freelance_webhook_events", "error")
    op.drop_column("freelance_webhook_events", "outcome")
    op.drop_column("freelance_webhook_events", "stripe_event_id")

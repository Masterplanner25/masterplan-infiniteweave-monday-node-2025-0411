"""add_wait_condition_to_execution_unit

Revision ID: h1i2j3k4l5m6
Revises: g5h6i7j8k9l0
Create Date: 2026-04-06 00:00:00.000000

Adds wait_condition JSONB column to execution_units.

Stored when an EU enters "waiting" status; cleared on resume.
Shape: {type, trigger_at, event_name, correlation_id}

See core/wait_condition.py for the WaitCondition dataclass.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "h1i2j3k4l5m6"
down_revision = "g5h6i7j8k9l0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_units",
        sa.Column("wait_condition", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("execution_units", "wait_condition")

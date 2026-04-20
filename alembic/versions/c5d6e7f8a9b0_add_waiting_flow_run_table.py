"""add waiting_flow_runs table

Revision ID: c5d6e7f8a9b0
Revises: b00a44e2b823
Create Date: 2026-04-19 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b00a44e2b823"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "waiting_flow_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eu_id", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("instance_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_waiting_flow_runs_event_type",
        "waiting_flow_runs",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_waiting_flow_runs_timeout_at",
        "waiting_flow_runs",
        ["timeout_at"],
        unique=False,
    )
    op.create_index(
        "ix_waiting_flow_runs_correlation",
        "waiting_flow_runs",
        ["correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_waiting_flow_runs_correlation", table_name="waiting_flow_runs")
    op.drop_index("ix_waiting_flow_runs_timeout_at", table_name="waiting_flow_runs")
    op.drop_index("ix_waiting_flow_runs_event_type", table_name="waiting_flow_runs")
    op.drop_table("waiting_flow_runs")

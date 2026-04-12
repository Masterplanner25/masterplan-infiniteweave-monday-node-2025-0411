"""watcher_signal_user_id

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-24

Adds user_id (nullable) to watcher_signals so focus_quality KPI can be
calculated per-user (Sprint N+5 Phase 1).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watcher_signals",
        sa.Column("user_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_watcher_signals_user_id",
        "watcher_signals",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_watcher_signals_user_id", table_name="watcher_signals")
    op.drop_column("watcher_signals", "user_id")

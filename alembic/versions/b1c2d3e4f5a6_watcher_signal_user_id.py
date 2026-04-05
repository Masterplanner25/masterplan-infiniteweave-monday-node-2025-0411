"""Compatibility mirror for legacy path-based tests.

Canonical migration lives in ``AINDY/alembic/versions/b1c2d3e4f5a6_watcher_signal_user_id.py``.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

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

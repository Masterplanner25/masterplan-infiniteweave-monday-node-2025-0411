"""Add delta engine snapshots

Revision ID: 0f283bba22b9
Revises: c6e5d4f3b2a1
Create Date: 2026-03-23 23:56:43.018575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f283bba22b9'
down_revision: Union[str, None] = 'c6e5d4f3b2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "drop_points",
        sa.Column("narrative_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "drop_points",
        sa.Column("velocity_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "drop_points",
        sa.Column("spread_score", sa.Float(), nullable=True),
    )

    op.add_column(
        "pings",
        sa.Column("strength", sa.Float(), nullable=False, server_default=sa.text("1.0")),
    )
    op.add_column(
        "pings",
        sa.Column("connection_type", sa.String(), nullable=False, server_default="direct"),
    )

    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("drop_point_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("narrative_score", sa.Float(), nullable=False),
        sa.Column("velocity_score", sa.Float(), nullable=False),
        sa.Column("spread_score", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_score_snapshots_drop_point_id",
        "score_snapshots",
        ["drop_point_id"],
    )
    op.create_index(
        "ix_score_snapshots_timestamp",
        "score_snapshots",
        ["timestamp"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_score_snapshots_timestamp", table_name="score_snapshots")
    op.drop_index("ix_score_snapshots_drop_point_id", table_name="score_snapshots")
    op.drop_table("score_snapshots")
    op.drop_column("pings", "connection_type")
    op.drop_column("pings", "strength")
    op.drop_column("drop_points", "spread_score")
    op.drop_column("drop_points", "velocity_score")
    op.drop_column("drop_points", "narrative_score")

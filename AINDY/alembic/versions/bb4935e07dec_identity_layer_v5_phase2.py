"""identity_layer_v5_phase2

Revision ID: bb4935e07dec
Revises: 5b14b05e179f
Create Date: 2026-03-18 23:38:45.753265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bb4935e07dec'
down_revision: Union[str, None] = '5b14b05e179f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_identity",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("tone", sa.String(), nullable=True),
        sa.Column("communication_notes", sa.Text(), nullable=True),
        sa.Column("preferred_languages", sa.JSON(), nullable=True, server_default="[]"),
        sa.Column("preferred_tools", sa.JSON(), nullable=True, server_default="[]"),
        sa.Column("avoided_tools", sa.JSON(), nullable=True, server_default="[]"),
        sa.Column("risk_tolerance", sa.String(), nullable=True),
        sa.Column("speed_vs_quality", sa.String(), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("learning_style", sa.String(), nullable=True),
        sa.Column("detail_preference", sa.String(), nullable=True),
        sa.Column("learning_notes", sa.Text(), nullable=True),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evolution_log", sa.JSON(), nullable=True, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_identity")

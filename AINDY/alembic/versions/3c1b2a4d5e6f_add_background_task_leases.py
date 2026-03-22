"""add background task leases

Revision ID: 3c1b2a4d5e6f
Revises: cb417760d319
Create Date: 2026-03-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3c1b2a4d5e6f"
down_revision: Union[str, None] = "cb417760d319"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "background_task_leases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_background_task_leases_name"), "background_task_leases", ["name"], unique=False)
    op.create_index(op.f("ix_background_task_leases_owner_id"), "background_task_leases", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_background_task_leases_owner_id"), table_name="background_task_leases")
    op.drop_index(op.f("ix_background_task_leases_name"), table_name="background_task_leases")
    op.drop_table("background_task_leases")

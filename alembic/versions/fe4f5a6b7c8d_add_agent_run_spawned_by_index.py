"""add_agent_run_spawned_by_index

Revision ID: fe4f5a6b7c8d
Revises: fd3e4f5a6b7c
Create Date: 2026-04-24 19:52:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "fe4f5a6b7c8d"
down_revision: Union[str, None] = "fd3e4f5a6b7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_agent_runs_spawned_by_agent_id"),
        "agent_runs",
        ["spawned_by_agent_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_spawned_by_agent_id"), table_name="agent_runs")

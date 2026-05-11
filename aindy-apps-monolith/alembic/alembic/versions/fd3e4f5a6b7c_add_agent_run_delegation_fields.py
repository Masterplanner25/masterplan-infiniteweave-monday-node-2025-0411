"""add_agent_run_delegation_fields

Revision ID: fd3e4f5a6b7c
Revises: fc2d3e4f5a6b
Create Date: 2026-04-24 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "fd3e4f5a6b7c"
down_revision: Union[str, None] = "fc2d3e4f5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("spawned_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("coordination_role", sa.String(length=16), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_parent_run_id",
        "agent_runs",
        "agent_runs",
        ["parent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_runs_spawned_by_agent_id",
        "agent_runs",
        "agent_registry",
        ["spawned_by_agent_id"],
        ["agent_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_runs_parent_run_id",
        "agent_runs",
        ["parent_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_parent_run_id", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_spawned_by_agent_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_parent_run_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "coordination_role")
    op.drop_column("agent_runs", "spawned_by_agent_id")
    op.drop_column("agent_runs", "parent_run_id")

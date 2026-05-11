"""agent_run_flow_run_id

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-03-25

Adds flow_run_id (nullable VARCHAR) to agent_runs so that each AgentRun can
reference the PersistentFlowRunner FlowRun that executed it (Sprint N+6
Deterministic Agent).  No FK constraint — FlowRun rows live in flow_runs
which may not be available in all environments.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("flow_run_id", sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "flow_run_id")

"""Compatibility mirror of the canonical AINDY migration.

This file exists for legacy path-based tests that still read root-level
``alembic/versions/*`` paths. The authoritative migration content lives under
``AINDY/alembic/versions/``.
"""

"""agent_run_replayed_from_run_id

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-03-25

Adds replayed_from_run_id (nullable VARCHAR) to agent_runs so that each
replayed AgentRun can reference the original run it was created from
(Sprint N+7 Agent Observability - /replay endpoint).
No FK constraint - referenced run may have been purged.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("replayed_from_run_id", sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "replayed_from_run_id")

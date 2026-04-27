"""add flow link foreign keys

Revision ID: 5e7f901b2c3d
Revises: 4d6e8f0a1b2c
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5e7f901b2c3d"
down_revision: Union[str, None] = "4d6e8f0a1b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve audit rows by nulling soft links that already point at missing
    # flow_runs; waiting_flow_runs entries must be removed because the row is
    # purely a child registration record.
    op.execute(
        """
        UPDATE agent_runs
        SET flow_run_id = NULL
        WHERE flow_run_id IS NOT NULL
          AND flow_run_id NOT IN (SELECT id FROM flow_runs)
        """
    )
    op.execute(
        """
        UPDATE execution_units
        SET flow_run_id = NULL
        WHERE flow_run_id IS NOT NULL
          AND flow_run_id NOT IN (SELECT id FROM flow_runs)
        """
    )
    op.execute(
        """
        DELETE FROM waiting_flow_runs
        WHERE run_id NOT IN (SELECT id FROM flow_runs)
        """
    )

    op.create_foreign_key(
        "fk_agent_runs_flow_run_id_flow_runs",
        "agent_runs",
        "flow_runs",
        ["flow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_execution_units_flow_run_id_flow_runs",
        "execution_units",
        "flow_runs",
        ["flow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_waiting_flow_runs_run_id_flow_runs",
        "waiting_flow_runs",
        "flow_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_waiting_flow_runs_run_id_flow_runs",
        "waiting_flow_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_execution_units_flow_run_id_flow_runs",
        "execution_units",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_runs_flow_run_id_flow_runs",
        "agent_runs",
        type_="foreignkey",
    )

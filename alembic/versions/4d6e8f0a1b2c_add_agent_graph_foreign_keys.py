"""add agent graph foreign keys

Revision ID: 4d6e8f0a1b2c
Revises: 3c5d7e9f1a2b
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4d6e8f0a1b2c"
down_revision: Union[str, None] = "3c5d7e9f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove child rows that already lost their parent before adding hard FKs.
    op.execute(
        """
        DELETE FROM agent_steps
        WHERE run_id IS NOT NULL
          AND run_id NOT IN (SELECT id FROM agent_runs)
        """
    )
    op.execute(
        """
        DELETE FROM agent_events
        WHERE run_id IS NOT NULL
          AND run_id NOT IN (SELECT id FROM agent_runs)
        """
    )
    op.execute(
        """
        DELETE FROM agent_capability_mappings
        WHERE capability_id IS NOT NULL
          AND capability_id NOT IN (SELECT id FROM capabilities)
        """
    )
    op.execute(
        """
        UPDATE agent_capability_mappings
        SET agent_run_id = NULL
        WHERE agent_run_id IS NOT NULL
          AND agent_run_id NOT IN (SELECT id FROM agent_runs)
        """
    )

    op.create_foreign_key(
        "fk_agent_steps_run_id_agent_runs",
        "agent_steps",
        "agent_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_events_run_id_agent_runs",
        "agent_events",
        "agent_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_capability_mappings_capability_id_capabilities",
        "agent_capability_mappings",
        "capabilities",
        ["capability_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_capability_mappings_agent_run_id_agent_runs",
        "agent_capability_mappings",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_capability_mappings_agent_run_id_agent_runs",
        "agent_capability_mappings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_capability_mappings_capability_id_capabilities",
        "agent_capability_mappings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_events_run_id_agent_runs",
        "agent_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_steps_run_id_agent_runs",
        "agent_steps",
        type_="foreignkey",
    )

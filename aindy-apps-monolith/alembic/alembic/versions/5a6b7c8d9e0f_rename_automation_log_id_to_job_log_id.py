"""rename automation_log_id to job_log_id

Revision ID: 5a6b7c8d9e0f
Revises: 4b7c8d9e0f11
Create Date: 2026-04-18

SAFETY REVIEW — changes made vs raw autogenerate
=================================================
1. USED ALTER TABLE … RENAME COLUMN (via op.alter_column new_column_name)
   WHY: Pure metadata rename in PostgreSQL — instant, no table rewrite,
   no data loss.  Safer than add + UPDATE + drop when a FK or index is
   involved.

2. DROPPED FK before rename on flow_runs
   WHY: The ORM model (FlowRun) no longer has a FK to automation_logs; the
   FK was inherited from the original flow_engine_phase_b migration that
   referenced the automation_logs table.  The new job_log_id column
   references job_logs (a looser coupling via String, no FK constraint),
   matching the current model definition.

3. INDEX RENAME via ALTER INDEX … RENAME TO (raw SQL)
   WHY: op.alter_column does not rename the index that backs a column with
   index=True.  We rename explicitly so the index name stays consistent
   with Alembic's naming convention and future autogenerate runs are silent.

4. strategies indexes NOT touched here
   WHY: ix_strategies_intent_type and ix_strategies_user_id exist in the DB
   and are legitimate.  The false-positive removal signal was caused by the
   ORM model lacking index=True on those columns.  That annotation has been
   added directly to apps/rippletrace/strategy.py so that future
   autogenerate runs recognise the indexes as intentional.

Affected tables: autonomy_decisions, flow_runs
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a6b7c8d9e0f"
down_revision: Union[str, Sequence[str], None] = "4b7c8d9e0f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── autonomy_decisions ──────────────────────────────────────────────────────
    # Rename automation_log_id → job_log_id (instant PG metadata rename)
    op.alter_column(
        "autonomy_decisions",
        "automation_log_id",
        new_column_name="job_log_id",
    )
    # Rename the backing index to match the new column name
    op.execute(
        "ALTER INDEX IF EXISTS ix_autonomy_decisions_automation_log_id "
        "RENAME TO ix_autonomy_decisions_job_log_id"
    )

    # ── flow_runs ───────────────────────────────────────────────────────────────
    # Drop the FK to automation_logs — FlowRun.job_log_id is a plain String
    # with no FK constraint in the current model
    op.drop_constraint(
        "flow_runs_automation_log_id_fkey",
        "flow_runs",
        type_="foreignkey",
    )
    # Rename automation_log_id → job_log_id
    op.alter_column(
        "flow_runs",
        "automation_log_id",
        new_column_name="job_log_id",
    )


def downgrade() -> None:
    # ── flow_runs ───────────────────────────────────────────────────────────────
    op.alter_column(
        "flow_runs",
        "job_log_id",
        new_column_name="automation_log_id",
    )
    op.create_foreign_key(
        "flow_runs_automation_log_id_fkey",
        "flow_runs",
        "automation_logs",
        ["automation_log_id"],
        ["id"],
    )

    # ── autonomy_decisions ──────────────────────────────────────────────────────
    op.execute(
        "ALTER INDEX IF EXISTS ix_autonomy_decisions_job_log_id "
        "RENAME TO ix_autonomy_decisions_automation_log_id"
    )
    op.alter_column(
        "autonomy_decisions",
        "job_log_id",
        new_column_name="automation_log_id",
    )

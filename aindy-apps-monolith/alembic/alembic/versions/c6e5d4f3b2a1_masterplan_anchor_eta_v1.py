"""masterplan_anchor_eta_v1

Adds anchor + ETA projection columns to master_plans:
  anchor_date               — user-declared milestone date
  goal_value                — numeric goal (e.g. 100000.0)
  goal_unit                 — unit label (e.g. "USD", "tasks")
  goal_description          — human-readable goal summary
  projected_completion_date — ETA computed by eta_service
  current_velocity          — tasks/day rolling 14-day average
  days_ahead_behind         — positive=ahead, negative=behind
  eta_last_calculated       — timestamp of last ETA computation
  eta_confidence            — "high" | "medium" | "low" | "insufficient_data"

Revision ID: c6e5d4f3b2a1
Revises: b5d4e3f2c1a0
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa

revision = "c6e5d4f3b2a1"
down_revision = "b5d4e3f2c1a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("master_plans", sa.Column("anchor_date", sa.DateTime(), nullable=True))
    op.add_column("master_plans", sa.Column("goal_value", sa.Float(), nullable=True))
    op.add_column("master_plans", sa.Column("goal_unit", sa.String(), nullable=True))
    op.add_column("master_plans", sa.Column("goal_description", sa.Text(), nullable=True))
    op.add_column("master_plans", sa.Column("projected_completion_date", sa.Date(), nullable=True))
    op.add_column("master_plans", sa.Column("current_velocity", sa.Float(), nullable=True))
    op.add_column("master_plans", sa.Column("days_ahead_behind", sa.Integer(), nullable=True))
    op.add_column(
        "master_plans",
        sa.Column("eta_last_calculated", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("master_plans", sa.Column("eta_confidence", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("master_plans", "eta_confidence")
    op.drop_column("master_plans", "eta_last_calculated")
    op.drop_column("master_plans", "days_ahead_behind")
    op.drop_column("master_plans", "current_velocity")
    op.drop_column("master_plans", "projected_completion_date")
    op.drop_column("master_plans", "goal_description")
    op.drop_column("master_plans", "goal_unit")
    op.drop_column("master_plans", "goal_value")
    op.drop_column("master_plans", "anchor_date")

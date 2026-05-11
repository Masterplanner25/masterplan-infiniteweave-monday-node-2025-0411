"""add masterplan task automation fields

Revision ID: b1c2d3e4f5a7
Revises: f0a1b2c3d4e5
Create Date: 2025-02-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("masterplan_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("automation_type", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("automation_config", sa.JSON(), nullable=True))
    op.create_index(op.f("ix_tasks_masterplan_id"), "tasks", ["masterplan_id"], unique=False)
    op.create_foreign_key(
        "fk_tasks_masterplan_id_master_plans",
        "tasks",
        "master_plans",
        ["masterplan_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_masterplan_id_master_plans", "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_masterplan_id"), table_name="tasks")
    op.drop_column("tasks", "automation_config")
    op.drop_column("tasks", "automation_type")
    op.drop_column("tasks", "masterplan_id")

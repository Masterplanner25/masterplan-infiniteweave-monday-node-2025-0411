"""add task dependency graph fields

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2025-04-13 03:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("parent_task_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("depends_on", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("tasks", sa.Column("dependency_type", sa.String(length=32), nullable=False, server_default="hard"))
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"], unique=False)
    op.create_foreign_key(
        "fk_tasks_parent_task_id_tasks",
        "tasks",
        "tasks",
        ["parent_task_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_parent_task_id_tasks", "tasks", type_="foreignkey")
    op.drop_index("ix_tasks_parent_task_id", table_name="tasks")
    op.drop_column("tasks", "dependency_type")
    op.drop_column("tasks", "depends_on")
    op.drop_column("tasks", "parent_task_id")

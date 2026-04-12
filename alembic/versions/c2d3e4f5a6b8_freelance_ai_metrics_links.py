"""add freelance ai metrics and links

Revision ID: c2d3e4f5a6b8
Revises: b1c2d3e4f5a7
Create Date: 2025-02-24 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c2d3e4f5a6b8"
down_revision = "b1c2d3e4f5a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("freelance_orders", sa.Column("masterplan_id", sa.Integer(), nullable=True))
    op.add_column("freelance_orders", sa.Column("task_id", sa.Integer(), nullable=True))
    op.add_column("freelance_orders", sa.Column("automation_log_id", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("automation_type", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("automation_config", sa.JSON(), nullable=True))
    op.add_column("freelance_orders", sa.Column("delivery_quality_score", sa.Float(), nullable=True))
    op.add_column("freelance_orders", sa.Column("time_to_completion_seconds", sa.Float(), nullable=True))
    op.add_column("freelance_orders", sa.Column("income_efficiency", sa.Float(), nullable=True))
    op.add_column("freelance_orders", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("freelance_orders", sa.Column("delivered_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_freelance_orders_masterplan_id"), "freelance_orders", ["masterplan_id"], unique=False)
    op.create_index(op.f("ix_freelance_orders_task_id"), "freelance_orders", ["task_id"], unique=False)
    op.create_index(op.f("ix_freelance_orders_automation_log_id"), "freelance_orders", ["automation_log_id"], unique=False)
    op.create_foreign_key("fk_freelance_orders_masterplan_id", "freelance_orders", "master_plans", ["masterplan_id"], ["id"])
    op.create_foreign_key("fk_freelance_orders_task_id", "freelance_orders", "tasks", ["task_id"], ["id"])
    op.create_foreign_key("fk_freelance_orders_automation_log_id", "freelance_orders", "automation_logs", ["automation_log_id"], ["id"])
    op.add_column("client_feedback", sa.Column("success_signal", sa.Float(), nullable=True))
    op.add_column("revenue_metrics", sa.Column("avg_delivery_quality", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("revenue_metrics", "avg_delivery_quality")
    op.drop_column("client_feedback", "success_signal")
    op.drop_constraint("fk_freelance_orders_automation_log_id", "freelance_orders", type_="foreignkey")
    op.drop_constraint("fk_freelance_orders_task_id", "freelance_orders", type_="foreignkey")
    op.drop_constraint("fk_freelance_orders_masterplan_id", "freelance_orders", type_="foreignkey")
    op.drop_index(op.f("ix_freelance_orders_automation_log_id"), table_name="freelance_orders")
    op.drop_index(op.f("ix_freelance_orders_task_id"), table_name="freelance_orders")
    op.drop_index(op.f("ix_freelance_orders_masterplan_id"), table_name="freelance_orders")
    op.drop_column("freelance_orders", "delivered_at")
    op.drop_column("freelance_orders", "started_at")
    op.drop_column("freelance_orders", "income_efficiency")
    op.drop_column("freelance_orders", "time_to_completion_seconds")
    op.drop_column("freelance_orders", "delivery_quality_score")
    op.drop_column("freelance_orders", "automation_config")
    op.drop_column("freelance_orders", "automation_type")
    op.drop_column("freelance_orders", "automation_log_id")
    op.drop_column("freelance_orders", "task_id")
    op.drop_column("freelance_orders", "masterplan_id")

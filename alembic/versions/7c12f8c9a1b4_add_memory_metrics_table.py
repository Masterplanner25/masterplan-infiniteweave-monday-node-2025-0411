"""add memory_metrics table

Revision ID: 7c12f8c9a1b4
Revises: c7602451aabb
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7c12f8c9a1b4"
down_revision = "c7602451aabb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=True),
        sa.Column("impact_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("memory_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_similarity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_metrics_user_id", "memory_metrics", ["user_id"], unique=False)
    op.create_index("ix_memory_metrics_task_type", "memory_metrics", ["task_type"], unique=False)


def downgrade():
    op.drop_index("ix_memory_metrics_task_type", table_name="memory_metrics")
    op.drop_index("ix_memory_metrics_user_id", table_name="memory_metrics")
    op.drop_table("memory_metrics")

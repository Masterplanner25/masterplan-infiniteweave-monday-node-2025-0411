"""add_user_kpi_weights

Revision ID: fb1c2d3e4f5a
Revises: fa0b1c2d3e4f
Create Date: 2026-04-24 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "fb1c2d3e4f5a"
down_revision: Union[str, None] = "fa0b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_kpi_weights",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("execution_speed_weight", sa.Float(), nullable=False, server_default="0.25"),
        sa.Column("decision_efficiency_weight", sa.Float(), nullable=False, server_default="0.25"),
        sa.Column("ai_productivity_boost_weight", sa.Float(), nullable=False, server_default="0.20"),
        sa.Column("focus_quality_weight", sa.Float(), nullable=False, server_default="0.15"),
        sa.Column("masterplan_progress_weight", sa.Float(), nullable=False, server_default="0.15"),
        sa.Column("adapted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_adapted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_kpi_weights_user_id"), "user_kpi_weights", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_kpi_weights_user_id"), table_name="user_kpi_weights")
    op.drop_table("user_kpi_weights")

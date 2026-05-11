"""add infinity loop adjustment and feedback tables

Revision ID: f1e2d3c4b5a6
Revises: e1f2a3b4c5d6
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1e2d3c4b5a6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("feedback_value", sa.Integer(), nullable=False),
        sa.Column("feedback_text", sa.String(), nullable=True),
        sa.Column("loop_adjustment_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_feedback_user_id"), "user_feedback", ["user_id"], unique=False)

    op.create_table(
        "loop_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("trigger_event", sa.String(), nullable=False),
        sa.Column("score_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision_type", sa.String(), nullable=False),
        sa.Column("adjustment_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_loop_adjustments_user_id"), "loop_adjustments", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_loop_adjustments_user_id"), table_name="loop_adjustments")
    op.drop_table("loop_adjustments")
    op.drop_index(op.f("ix_user_feedback_user_id"), table_name="user_feedback")
    op.drop_table("user_feedback")

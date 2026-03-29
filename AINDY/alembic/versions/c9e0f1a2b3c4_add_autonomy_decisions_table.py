"""add autonomy decisions table

Revision ID: c9e0f1a2b3c4
Revises: b8c9d0e1f2a3
Create Date: 2025-04-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c9e0f1a2b3c4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autonomy_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("automation_log_id", sa.String(), nullable=True),
        sa.Column("trigger_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_autonomy_decisions_user_id", "autonomy_decisions", ["user_id"], unique=False)
    op.create_index("ix_autonomy_decisions_trigger_type", "autonomy_decisions", ["trigger_type"], unique=False)
    op.create_index("ix_autonomy_decisions_trigger_source", "autonomy_decisions", ["trigger_source"], unique=False)
    op.create_index("ix_autonomy_decisions_decision", "autonomy_decisions", ["decision"], unique=False)
    op.create_index("ix_autonomy_decisions_trace_id", "autonomy_decisions", ["trace_id"], unique=False)
    op.create_index("ix_autonomy_decisions_automation_log_id", "autonomy_decisions", ["automation_log_id"], unique=False)
    op.create_index("ix_autonomy_decisions_created_at", "autonomy_decisions", ["created_at"], unique=False)
    op.create_index(
        "ix_autonomy_decisions_user_created_at",
        "autonomy_decisions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_autonomy_decisions_trace_created_at",
        "autonomy_decisions",
        ["trace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_autonomy_decisions_trace_created_at", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_user_created_at", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_created_at", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_automation_log_id", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_trace_id", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_decision", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_trigger_source", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_trigger_type", table_name="autonomy_decisions")
    op.drop_index("ix_autonomy_decisions_user_id", table_name="autonomy_decisions")
    op.drop_table("autonomy_decisions")

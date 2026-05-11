"""automation_log_flow_engine_phase_a

Revision ID: 37020d1c3951
Revises: 2359cded7445
Create Date: 2026-03-22 20:16:58.343412

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37020d1c3951'
down_revision: Union[str, None] = '2359cded7445'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_logs_status", "automation_logs", ["status"])
    op.create_index("ix_automation_logs_user_id", "automation_logs", ["user_id"])
    op.create_index("ix_automation_logs_source", "automation_logs", ["source"])


def downgrade() -> None:
    op.drop_index("ix_automation_logs_source", table_name="automation_logs")
    op.drop_index("ix_automation_logs_user_id", table_name="automation_logs")
    op.drop_index("ix_automation_logs_status", table_name="automation_logs")
    op.drop_table("automation_logs")

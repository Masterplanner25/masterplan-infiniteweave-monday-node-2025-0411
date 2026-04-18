"""add_platform_job_logs

Revision ID: 3f6a9b2c4d10
Revises: 2c6054da62a1
Create Date: 2026-04-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "3f6a9b2c4d10"
down_revision: Union[str, Sequence[str], None] = "2c6054da62a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("job_name", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_logs_user_id", "job_logs", ["user_id"])
    op.create_index("ix_job_logs_trace_id", "job_logs", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_job_logs_trace_id", table_name="job_logs")
    op.drop_index("ix_job_logs_user_id", table_name="job_logs")
    op.drop_table("job_logs")

"""add_nodus_scheduled_jobs

Adds nodus_scheduled_jobs table for POST /platform/nodus/schedule.

Each row persists one cron-scheduled Nodus script so schedules survive
process restarts.  Active rows are restored into APScheduler on startup
by nodus_schedule_service.restore_nodus_scheduled_jobs().

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodus_scheduled_jobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("job_name", sa.String(256), nullable=True),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("script_name", sa.String(128), nullable=True),
        sa.Column("cron_expression", sa.String(128), nullable=False),
        sa.Column("input_payload", JSON(), nullable=True),
        sa.Column("error_policy", sa.String(16), nullable=False, server_default="fail"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(16), nullable=True),
        sa.Column("last_run_log_id", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_nodus_scheduled_jobs_user_id",
        "nodus_scheduled_jobs",
        ["user_id"],
    )
    op.create_index(
        "ix_nodus_scheduled_jobs_is_active",
        "nodus_scheduled_jobs",
        ["is_active"],
    )
    op.create_index(
        "ix_nodus_scheduled_jobs_user_active",
        "nodus_scheduled_jobs",
        ["user_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_nodus_scheduled_jobs_user_active", table_name="nodus_scheduled_jobs")
    op.drop_index("ix_nodus_scheduled_jobs_is_active", table_name="nodus_scheduled_jobs")
    op.drop_index("ix_nodus_scheduled_jobs_user_id", table_name="nodus_scheduled_jobs")
    op.drop_table("nodus_scheduled_jobs")

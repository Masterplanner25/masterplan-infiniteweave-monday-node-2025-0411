"""add_tenant_resource_fields_to_execution_units

Extends execution_units with tenant isolation and resource tracking columns
required by the A.I.N.D.Y. OS layer (Sprint: OS Isolation + Scheduler).

New columns
-----------
  tenant_id    String(128)  — tenant owner (== user_id in single-user model)
  cpu_time_ms  Integer      — accumulated CPU wall-time for this execution
  memory_bytes BigInteger   — peak memory high-water mark (bytes)
  syscall_count Integer     — total syscall dispatches for this execution
  priority     String(16)   — scheduling priority: low | normal | high
  quota_group  String(64)   — optional quota-group tag for policy overrides

Revision ID: f4g5h6i7j8k9
Revises: e3f4a5b6c7d8
Create Date: 2026-04-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f4g5h6i7j8k9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_units",
        sa.Column("tenant_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "execution_units",
        sa.Column("cpu_time_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "execution_units",
        sa.Column("memory_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "execution_units",
        sa.Column("syscall_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "execution_units",
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "execution_units",
        sa.Column("quota_group", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_eu_tenant_id",
        "execution_units",
        ["tenant_id"],
    )
    op.create_index(
        "ix_eu_tenant_priority",
        "execution_units",
        ["tenant_id", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_eu_tenant_priority", table_name="execution_units")
    op.drop_index("ix_eu_tenant_id", table_name="execution_units")
    op.drop_column("execution_units", "quota_group")
    op.drop_column("execution_units", "priority")
    op.drop_column("execution_units", "syscall_count")
    op.drop_column("execution_units", "memory_bytes")
    op.drop_column("execution_units", "cpu_time_ms")
    op.drop_column("execution_units", "tenant_id")

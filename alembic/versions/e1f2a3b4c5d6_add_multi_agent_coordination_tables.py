"""add multi agent coordination tables

Revision ID: e9f0a1b2c3d4
Revises: d0e1f2a3b4c5
Create Date: 2025-04-13 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e9f0a1b2c3d4"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_registry",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("current_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("load", sa.Float(), nullable=False, server_default="0"),
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default="healthy"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("agent_id"),
    )
    op.create_index("ix_agent_registry_load", "agent_registry", ["load"], unique=False)
    op.create_index("ix_agent_registry_health_status", "agent_registry", ["health_status"], unique=False)
    op.create_index("ix_agent_registry_last_seen", "agent_registry", ["last_seen"], unique=False)

    op.add_column("system_events", sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_system_events_agent_id_agent_registry",
        "system_events",
        "agent_registry",
        ["agent_id"],
        ["agent_id"],
    )
    op.create_index("ix_system_events_agent_id", "system_events", ["agent_id"], unique=False)

    op.add_column("memory_nodes", sa.Column("visibility", sa.String(length=16), nullable=True))
    op.execute("UPDATE memory_nodes SET visibility = CASE WHEN is_shared THEN 'shared' ELSE 'private' END WHERE visibility IS NULL")
    op.alter_column("memory_nodes", "visibility", nullable=False, server_default="private")


def downgrade() -> None:
    op.alter_column("memory_nodes", "visibility", server_default=None)
    op.drop_column("memory_nodes", "visibility")
    op.drop_index("ix_system_events_agent_id", table_name="system_events")
    op.drop_constraint("fk_system_events_agent_id_agent_registry", "system_events", type_="foreignkey")
    op.drop_column("system_events", "agent_id")
    op.drop_index("ix_agent_registry_last_seen", table_name="agent_registry")
    op.drop_index("ix_agent_registry_health_status", table_name="agent_registry")
    op.drop_index("ix_agent_registry_load", table_name="agent_registry")
    op.drop_table("agent_registry")

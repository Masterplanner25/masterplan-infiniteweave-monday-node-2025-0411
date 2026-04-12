"""agent capability policy models

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs",
        sa.Column("agent_type", sa.String(length=64), nullable=False, server_default="default"),
    )
    op.add_column(
        "agent_runs",
        sa.Column("execution_token", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_capabilities_name", "capabilities", ["name"], unique=True)
    op.create_index("ix_capabilities_risk_level", "capabilities", ["risk_level"], unique=False)

    op.create_table(
        "agent_capability_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", sa.String(length=64), nullable=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_capability_mappings_capability_id",
        "agent_capability_mappings",
        ["capability_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_capability_mappings_agent_type",
        "agent_capability_mappings",
        ["agent_type"],
        unique=False,
    )
    op.create_index(
        "ix_agent_capability_mappings_agent_run_id",
        "agent_capability_mappings",
        ["agent_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_capability_mappings_agent_type_capability",
        "agent_capability_mappings",
        ["agent_type", "capability_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_capability_mappings_run_capability",
        "agent_capability_mappings",
        ["agent_run_id", "capability_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO capabilities (id, name, description, risk_level, created_at, updated_at)
        VALUES
            (gen_random_uuid(), 'execute_flow', 'Start and continue a scoped workflow execution.', 'low', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'read_memory', 'Read memory and recall prior context.', 'low', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'write_memory', 'Create or update durable memory.', 'low', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'manage_tasks', 'Create or update task state.', 'low', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'external_api_call', 'Call an external LLM or web-backed integration.', 'medium', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'strategic_planning', 'Modify long-lived planning or genesis state.', 'high', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )

    op.alter_column("agent_runs", "agent_type", server_default=None)


def downgrade():
    op.drop_index("ix_agent_capability_mappings_run_capability", table_name="agent_capability_mappings")
    op.drop_index("ix_agent_capability_mappings_agent_type_capability", table_name="agent_capability_mappings")
    op.drop_index("ix_agent_capability_mappings_agent_run_id", table_name="agent_capability_mappings")
    op.drop_index("ix_agent_capability_mappings_agent_type", table_name="agent_capability_mappings")
    op.drop_index("ix_agent_capability_mappings_capability_id", table_name="agent_capability_mappings")
    op.drop_table("agent_capability_mappings")
    op.drop_index("ix_capabilities_risk_level", table_name="capabilities")
    op.drop_index("ix_capabilities_name", table_name="capabilities")
    op.drop_table("capabilities")
    op.drop_column("agent_runs", "execution_token")
    op.drop_column("agent_runs", "agent_type")

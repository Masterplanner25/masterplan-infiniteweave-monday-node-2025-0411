"""add_execution_units_table

Revision ID: a0b1c2d3e4f5
Revises: f2b3c4d5e6f7
Create Date: 2026-03-30

Unified ExecutionUnit abstraction — one queryable record per execution event
regardless of whether it originated as a Task, AgentRun, FlowRun, or Job.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a0b1c2d3e4f5"
down_revision = "f2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "execution_units",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        # Type and status
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        # Ownership
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Hierarchy — self-referential; nullable so root EUs have no parent
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("execution_units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Soft source link (no FK — supports integer Task PKs and UUID PKs)
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        # Execution links
        sa.Column("flow_run_id", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(72), nullable=True),
        # Memory
        sa.Column(
            "memory_context_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "output_memory_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Extra per-type metadata
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Single-column indexes (non-PK)
    op.create_index("ix_execution_units_type", "execution_units", ["type"])
    op.create_index("ix_execution_units_status", "execution_units", ["status"])
    op.create_index("ix_execution_units_user_id", "execution_units", ["user_id"])
    op.create_index("ix_execution_units_parent_id", "execution_units", ["parent_id"])
    op.create_index("ix_execution_units_source_id", "execution_units", ["source_id"])
    op.create_index("ix_execution_units_flow_run_id", "execution_units", ["flow_run_id"])
    op.create_index("ix_execution_units_correlation_id", "execution_units", ["correlation_id"])

    # Composite indexes
    op.create_index(
        "ix_eu_user_type_status",
        "execution_units",
        ["user_id", "type", "status"],
    )
    op.create_index(
        "ix_eu_source",
        "execution_units",
        ["source_type", "source_id"],
    )
    op.create_index(
        "ix_eu_correlation",
        "execution_units",
        ["correlation_id"],
    )


def downgrade():
    op.drop_index("ix_eu_correlation", table_name="execution_units")
    op.drop_index("ix_eu_source", table_name="execution_units")
    op.drop_index("ix_eu_user_type_status", table_name="execution_units")
    op.drop_index("ix_execution_units_correlation_id", table_name="execution_units")
    op.drop_index("ix_execution_units_flow_run_id", table_name="execution_units")
    op.drop_index("ix_execution_units_source_id", table_name="execution_units")
    op.drop_index("ix_execution_units_parent_id", table_name="execution_units")
    op.drop_index("ix_execution_units_user_id", table_name="execution_units")
    op.drop_index("ix_execution_units_status", table_name="execution_units")
    op.drop_index("ix_execution_units_type", table_name="execution_units")
    op.drop_table("execution_units")

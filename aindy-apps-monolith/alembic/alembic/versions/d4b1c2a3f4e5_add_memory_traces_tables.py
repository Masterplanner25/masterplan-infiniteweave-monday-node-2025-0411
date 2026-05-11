"""add memory_traces tables

Revision ID: d4b1c2a3f4e5
Revises: cc88b538c4a7
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d4b1c2a3f4e5"
down_revision = "cc88b538c4a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_traces_user_id", "memory_traces", ["user_id"], unique=False)

    op.create_table(
        "memory_trace_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["trace_id"], ["memory_traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["memory_nodes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("trace_id", "position", name="uq_trace_position"),
    )
    op.create_index("ix_memory_trace_nodes_trace_id", "memory_trace_nodes", ["trace_id"], unique=False)
    op.create_index("ix_memory_trace_nodes_node_id", "memory_trace_nodes", ["node_id"], unique=False)


def downgrade():
    op.drop_index("ix_memory_trace_nodes_node_id", table_name="memory_trace_nodes")
    op.drop_index("ix_memory_trace_nodes_trace_id", table_name="memory_trace_nodes")
    op.drop_table("memory_trace_nodes")
    op.drop_index("ix_memory_traces_user_id", table_name="memory_traces")
    op.drop_table("memory_traces")

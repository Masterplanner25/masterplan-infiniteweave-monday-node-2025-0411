"""add ripple-aware memory causality columns

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-26 13:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_nodes",
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("root_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("causal_depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("impact_score", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("memory_type", sa.String(length=32), nullable=False, server_default="insight"),
    )
    op.create_index("ix_memory_nodes_source_event_id", "memory_nodes", ["source_event_id"], unique=False)
    op.create_index("ix_memory_nodes_root_event_id", "memory_nodes", ["root_event_id"], unique=False)
    op.create_index("ix_memory_nodes_memory_type", "memory_nodes", ["memory_type"], unique=False)
    op.create_foreign_key(
        "fk_memory_nodes_source_event_id",
        "memory_nodes",
        "system_events",
        ["source_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_memory_nodes_root_event_id",
        "memory_nodes",
        "system_events",
        ["root_event_id"],
        ["id"],
    )
    op.execute("UPDATE memory_nodes SET causal_depth = 0 WHERE causal_depth IS NULL")
    op.execute("UPDATE memory_nodes SET impact_score = 0 WHERE impact_score IS NULL")
    op.execute("UPDATE memory_nodes SET memory_type = node_type WHERE memory_type IS NULL AND node_type IN ('decision', 'outcome', 'insight')")
    op.execute("UPDATE memory_nodes SET memory_type = 'insight' WHERE memory_type IS NULL")
    op.alter_column("memory_nodes", "causal_depth", server_default=None)
    op.alter_column("memory_nodes", "impact_score", server_default=None)
    op.alter_column("memory_nodes", "memory_type", server_default=None)

    op.add_column(
        "ripple_edges",
        sa.Column("target_memory_node_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("ripple_edges", "target_event_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_index("ix_ripple_edges_target_memory_node_id", "ripple_edges", ["target_memory_node_id"], unique=False)
    op.create_foreign_key(
        "fk_ripple_edges_target_memory_node_id",
        "ripple_edges",
        "memory_nodes",
        ["target_memory_node_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_ripple_edges_single_target",
        "ripple_edges",
        "(target_event_id IS NOT NULL) <> (target_memory_node_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ripple_edges_single_target", "ripple_edges", type_="check")
    op.drop_constraint("fk_ripple_edges_target_memory_node_id", "ripple_edges", type_="foreignkey")
    op.drop_index("ix_ripple_edges_target_memory_node_id", table_name="ripple_edges")
    op.alter_column("ripple_edges", "target_event_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column("ripple_edges", "target_memory_node_id")

    op.drop_constraint("fk_memory_nodes_root_event_id", "memory_nodes", type_="foreignkey")
    op.drop_constraint("fk_memory_nodes_source_event_id", "memory_nodes", type_="foreignkey")
    op.drop_index("ix_memory_nodes_memory_type", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_root_event_id", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_source_event_id", table_name="memory_nodes")
    op.drop_column("memory_nodes", "memory_type")
    op.drop_column("memory_nodes", "impact_score")
    op.drop_column("memory_nodes", "causal_depth")
    op.drop_column("memory_nodes", "root_event_id")
    op.drop_column("memory_nodes", "source_event_id")

"""multi_agent_memory_v5_phase3

Revision ID: a2ec23964f2c
Revises: bb4935e07dec
Create Date: 2026-03-19 21:14:56.288326

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2ec23964f2c'
down_revision: Union[str, None] = 'bb4935e07dec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.String(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "memory_namespace",
            sa.String(),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "memory_nodes",
        sa.Column("source_agent", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_memory_nodes_source_agent",
        "memory_nodes",
        ["source_agent"],
    )

    op.add_column(
        "memory_nodes",
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO agents
                (id, name, agent_type, description, memory_namespace, is_active)
            VALUES
                ('agent-arm-001', 'ARM', 'reasoning',
                 'Autonomous Reasoning Module — code analysis and generation',
                 'arm', true),
                ('agent-genesis-001', 'Genesis', 'strategic',
                 'Strategic planning and MasterPlan synthesis',
                 'genesis', true),
                ('agent-nodus-001', 'Nodus', 'execution',
                 'Nodus language task execution runtime',
                 'nodus', true),
                ('agent-leadgen-001', 'LeadGen', 'prospecting',
                 'Lead generation and prospecting',
                 'leadgen', true),
                ('agent-sylva-001', 'SYLVA', 'custom',
                 'Future collaborative agent — reserved namespace',
                 'sylva', false)
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memory_nodes_source_agent", table_name="memory_nodes")
    op.drop_column("memory_nodes", "is_shared")
    op.drop_column("memory_nodes", "source_agent")
    op.drop_table("agents")

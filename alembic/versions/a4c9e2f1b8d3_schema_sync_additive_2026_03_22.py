"""schema_sync_additive_2026_03_22

Adds indexes and constraints that are declared in ORM models but were missing
from the database. All operations are additive (CREATE INDEX / ADD CONSTRAINT).
No columns are dropped, no FKs are removed, no existing indexes are touched.

Skipped (known drift — documented in TECH_DEBT.md §15):
  - ix_memory_nodes_embedding_hnsw  (HNSW pgvector index — managed manually)
  - request_metrics_user_id_fkey    (FK removal — intentional, kept for now)
  - ix_request_metrics_path_created_at (composite index — kept)
  - background_task_leases constraint rename (too risky — kept)

Revision ID: a4c9e2f1b8d3
Revises: 37020d1c3951
Create Date: 2026-03-22 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c9e2f1b8d3'
down_revision: Union[str, None] = '37020d1c3951'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing indexes and constraints (additive only)."""
    # ix_master_plans_user_id — ORM declares index=True on user_id, DB lacks it
    op.create_index(
        op.f('ix_master_plans_user_id'),
        'master_plans', ['user_id'],
        unique=False,
    )

    # uq_memory_links_unique — unique index declared in memory_persistence.py ORM
    op.create_index(
        'uq_memory_links_unique',
        'memory_links',
        ['source_node_id', 'target_node_id', 'link_type'],
        unique=True,
    )

    # ix_memory_metrics_id — ORM declares index=True on primary key id column
    op.create_index(
        op.f('ix_memory_metrics_id'),
        'memory_metrics', ['id'],
        unique=False,
    )

    # uq_user_identity_user — UniqueConstraint in __table_args__, missing in DB
    op.create_unique_constraint(
        'uq_user_identity_user',
        'user_identity',
        ['user_id'],
    )


def downgrade() -> None:
    """Remove the indexes and constraints added in upgrade."""
    op.drop_constraint('uq_user_identity_user', 'user_identity', type_='unique')
    op.drop_index(op.f('ix_memory_metrics_id'), table_name='memory_metrics')
    op.drop_index('uq_memory_links_unique', table_name='memory_links')
    op.drop_index(op.f('ix_master_plans_user_id'), table_name='master_plans')

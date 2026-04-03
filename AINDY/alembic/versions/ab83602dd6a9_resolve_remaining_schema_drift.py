"""resolve_remaining_schema_drift

Revision ID: ab83602dd6a9
Revises: 045921eda2ca
Create Date: 2026-04-01 23:05:26.319835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab83602dd6a9'
down_revision: Union[str, None] = '045921eda2ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Remove outdated unique constraints ---
    op.drop_constraint(
        "capabilities_name_key",
        "capabilities",
        type_="unique"
    )

    op.drop_constraint(
        "goal_states_goal_id_key",
        "goal_states",
        type_="unique"
    )

    # --- Remove outdated HNSW index ---
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_embedding_hnsw")

def downgrade() -> None:
    """Downgrade schema."""
    # --- Restore unique constraints ---
    op.create_unique_constraint(
        "capabilities_name_key",
        "capabilities",
        ["name"]
    )

    op.create_unique_constraint(
        "goal_states_goal_id_key",
        "goal_states",
        ["goal_id"]
    )

    # --- Restore HNSW index ---
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_memory_nodes_embedding_hnsw
    ON memory_nodes
    USING hnsw (embedding vector_cosine_ops)
    """)
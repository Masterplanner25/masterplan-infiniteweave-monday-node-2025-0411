"""add_masterplan_genesis_session_uniqueness

Revision ID: 2d4f6a8b0c1d
Revises: 1b2c3d4e5f6a
Create Date: 2026-04-26 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d4f6a8b0c1d"
down_revision: Union[str, None] = "1b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_masterplan_genesis_session_id"
TABLE_NAME = "master_plans"
COLUMN_NAME = "linked_genesis_session_id"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            [COLUMN_NAME],
            unique=True,
            postgresql_where=sa.text(f"{COLUMN_NAME} IS NOT NULL"),
        )
    else:
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            [COLUMN_NAME],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)

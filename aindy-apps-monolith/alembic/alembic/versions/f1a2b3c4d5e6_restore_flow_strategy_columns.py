"""Restore flow engine strategy columns on strategies table

Revision ID: f1a2b3c4d5e6
Revises: 6047d041730b
Create Date: 2026-03-29 10:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "6047d041730b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("intent_type", sa.String(), nullable=True))
    op.add_column("strategies", sa.Column("flow", sa.JSON(), nullable=True))
    op.add_column("strategies", sa.Column("score", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("strategies", sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("strategies", sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("strategies", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "strategies",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.execute("UPDATE strategies SET intent_type = 'legacy_strategy' WHERE intent_type IS NULL")
    op.execute("UPDATE strategies SET flow = '{}'::json WHERE flow IS NULL")
    op.execute("UPDATE strategies SET score = 1.0 WHERE score IS NULL")
    op.execute("UPDATE strategies SET success_count = 0 WHERE success_count IS NULL")
    op.execute("UPDATE strategies SET failure_count = 0 WHERE failure_count IS NULL")
    op.execute("UPDATE strategies SET updated_at = NOW() WHERE updated_at IS NULL")

    op.alter_column("strategies", "intent_type", nullable=False)
    op.alter_column("strategies", "flow", nullable=False)

    op.create_index("ix_strategies_intent_type", "strategies", ["intent_type"], unique=False)
    op.create_index("ix_strategies_user_id", "strategies", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_strategies_user_id_users",
        "strategies",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("strategies", "score", server_default=None)
    op.alter_column("strategies", "success_count", server_default=None)
    op.alter_column("strategies", "failure_count", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_strategies_user_id_users", "strategies", type_="foreignkey")
    op.drop_index("ix_strategies_user_id", table_name="strategies")
    op.drop_index("ix_strategies_intent_type", table_name="strategies")
    op.drop_column("strategies", "updated_at")
    op.drop_column("strategies", "user_id")
    op.drop_column("strategies", "failure_count")
    op.drop_column("strategies", "success_count")
    op.drop_column("strategies", "score")
    op.drop_column("strategies", "flow")
    op.drop_column("strategies", "intent_type")

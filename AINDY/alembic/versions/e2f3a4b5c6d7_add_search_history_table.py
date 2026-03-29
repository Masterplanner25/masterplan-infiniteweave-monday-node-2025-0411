"""add search history table

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2025-02-24 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_search_history_id"), "search_history", ["id"], unique=False)
    op.create_index(op.f("ix_search_history_user_id"), "search_history", ["user_id"], unique=False)
    op.create_index(op.f("ix_search_history_query"), "search_history", ["query"], unique=False)
    op.create_index(op.f("ix_search_history_created_at"), "search_history", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_search_history_created_at"), table_name="search_history")
    op.drop_index(op.f("ix_search_history_query"), table_name="search_history")
    op.drop_index(op.f("ix_search_history_user_id"), table_name="search_history")
    op.drop_index(op.f("ix_search_history_id"), table_name="search_history")
    op.drop_table("search_history")

"""normalize_user_id_uuid

Revision ID: 2359cded7445
Revises: d2a7f4c1b9e8
Create Date: 2026-03-22 15:03:01.912816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2359cded7445'
down_revision: Union[str, None] = 'd2a7f4c1b9e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Null any non-UUID user_id values to allow safe cast
    op.execute(
        """
        UPDATE research_results
        SET user_id = NULL
        WHERE user_id IS NOT NULL
          AND user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
        """
    )
    op.execute(
        """
        UPDATE freelance_orders
        SET user_id = NULL
        WHERE user_id IS NOT NULL
          AND user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
        """
    )
    op.execute(
        """
        UPDATE client_feedback
        SET user_id = NULL
        WHERE user_id IS NOT NULL
          AND user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
        """
    )
    op.execute(
        """
        UPDATE drop_points
        SET user_id = NULL
        WHERE user_id IS NOT NULL
          AND user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
        """
    )
    op.execute(
        """
        UPDATE pings
        SET user_id = NULL
        WHERE user_id IS NOT NULL
          AND user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
        """
    )

    # Convert user_id columns to UUID and add FK constraints
    op.alter_column(
        "research_results",
        "user_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        nullable=True,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "freelance_orders",
        "user_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        nullable=True,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "client_feedback",
        "user_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        nullable=True,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "drop_points",
        "user_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        nullable=True,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "pings",
        "user_id",
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        nullable=True,
        postgresql_using="user_id::uuid",
    )

    op.create_foreign_key(
        "fk_research_results_user_id",
        "research_results",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_freelance_orders_user_id",
        "freelance_orders",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_client_feedback_user_id",
        "client_feedback",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_drop_points_user_id",
        "drop_points",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_pings_user_id",
        "pings",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_pings_user_id", "pings", type_="foreignkey")
    op.drop_constraint("fk_drop_points_user_id", "drop_points", type_="foreignkey")
    op.drop_constraint("fk_client_feedback_user_id", "client_feedback", type_="foreignkey")
    op.drop_constraint("fk_freelance_orders_user_id", "freelance_orders", type_="foreignkey")
    op.drop_constraint("fk_research_results_user_id", "research_results", type_="foreignkey")

    op.alter_column(
        "pings",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        nullable=True,
        postgresql_using="user_id::text",
    )
    op.alter_column(
        "drop_points",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        nullable=True,
        postgresql_using="user_id::text",
    )
    op.alter_column(
        "client_feedback",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        nullable=True,
        postgresql_using="user_id::text",
    )
    op.alter_column(
        "freelance_orders",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        nullable=True,
        postgresql_using="user_id::text",
    )
    op.alter_column(
        "research_results",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(),
        nullable=True,
        postgresql_using="user_id::text",
    )

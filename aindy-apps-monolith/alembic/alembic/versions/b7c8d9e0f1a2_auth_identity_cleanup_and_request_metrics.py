"""auth identity cleanup and request metrics baseline

Revision ID: b7c8d9e0f1a2
Revises: f3a4b5c6d7e8
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "request_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_request_metrics_request_id", "request_metrics", ["request_id"], unique=False)
    op.create_index("ix_request_metrics_user_id", "request_metrics", ["user_id"], unique=False)
    op.create_index("ix_request_metrics_path", "request_metrics", ["path"], unique=False)

    with op.batch_alter_table("canonical_metrics") as batch:
        batch.drop_column("user_id")
        batch.add_column(sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.create_index("ix_canonical_metrics_user_id", ["user_id"], unique=False)
        batch.create_foreign_key(
            "fk_canonical_metrics_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )

    with op.batch_alter_table("genesis_sessions") as batch:
        batch.drop_column("user_id")
        batch.add_column(sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.create_index("ix_genesis_sessions_user_id", ["user_id"], unique=False)
        batch.create_foreign_key(
            "fk_genesis_sessions_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )

    op.execute(
        """
        UPDATE genesis_sessions
        SET user_id = NULLIF(user_id_str, '')::uuid
        WHERE user_id_str ~* '^[0-9a-f-]{36}$'
        """
    )

    with op.batch_alter_table("genesis_sessions") as batch:
        batch.drop_column("user_id_str")


def downgrade():
    with op.batch_alter_table("genesis_sessions") as batch:
        batch.add_column(sa.Column("user_id_str", sa.String(), nullable=True))
        batch.drop_constraint("fk_genesis_sessions_user_id_users", type_="foreignkey")
        batch.drop_index("ix_genesis_sessions_user_id")
        batch.drop_column("user_id")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("canonical_metrics") as batch:
        batch.drop_constraint("fk_canonical_metrics_user_id_users", type_="foreignkey")
        batch.drop_index("ix_canonical_metrics_user_id")
        batch.drop_column("user_id")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    op.drop_index("ix_request_metrics_path", table_name="request_metrics")
    op.drop_index("ix_request_metrics_user_id", table_name="request_metrics")
    op.drop_index("ix_request_metrics_request_id", table_name="request_metrics")
    op.drop_table("request_metrics")

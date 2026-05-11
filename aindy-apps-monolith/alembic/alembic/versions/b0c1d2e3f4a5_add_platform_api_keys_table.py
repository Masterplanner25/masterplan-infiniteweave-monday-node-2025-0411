"""add_platform_api_keys_table

Revision ID: b0c1d2e3f4a5
Revises: a0b1c2d3e4f5
Create Date: 2026-03-31

Stores hashed platform API keys with scoped capabilities for external
system access.  Plaintext keys are never persisted — only the SHA-256
hash is stored.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b0c1d2e3f4a5"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Primary lookup index: key hash must be unique and fast to query on every request
    op.create_index(
        "ix_platform_api_keys_key_hash",
        "platform_api_keys",
        ["key_hash"],
        unique=True,
    )
    # Secondary index: listing all keys owned by a user
    op.create_index(
        "ix_platform_api_keys_user_id",
        "platform_api_keys",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_platform_api_keys_user_id", table_name="platform_api_keys")
    op.drop_index("ix_platform_api_keys_key_hash", table_name="platform_api_keys")
    op.drop_table("platform_api_keys")

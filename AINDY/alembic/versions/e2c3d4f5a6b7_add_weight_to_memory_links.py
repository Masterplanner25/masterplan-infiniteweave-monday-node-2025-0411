"""add weight to memory_links

Revision ID: e2c3d4f5a6b7
Revises: d4b1c2a3f4e5
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e2c3d4f5a6b7"
down_revision = "d4b1c2a3f4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memory_links", sa.Column("weight", sa.Float(), nullable=False, server_default="0.5"))

    op.execute(
        """
        UPDATE memory_links
        SET weight = CASE
            WHEN lower(strength) = 'low' THEN 0.3
            WHEN lower(strength) = 'medium' THEN 0.6
            WHEN lower(strength) = 'high' THEN 0.9
            ELSE 0.5
        END
        """
    )

    op.alter_column("memory_links", "weight", server_default=None)


def downgrade():
    op.drop_column("memory_links", "weight")

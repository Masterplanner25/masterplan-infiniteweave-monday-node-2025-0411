"""add freelance external delivery fields

Revision ID: d1e2f3a4b5c6
Revises: c2d3e4f5a6b8
Create Date: 2025-02-24 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c2d3e4f5a6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("freelance_orders", sa.Column("delivery_type", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("delivery_config", sa.JSON(), nullable=True))
    op.add_column("freelance_orders", sa.Column("delivery_status", sa.String(), nullable=True))
    op.add_column("freelance_orders", sa.Column("external_response", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("freelance_orders", "external_response")
    op.drop_column("freelance_orders", "delivery_status")
    op.drop_column("freelance_orders", "delivery_config")
    op.drop_column("freelance_orders", "delivery_type")

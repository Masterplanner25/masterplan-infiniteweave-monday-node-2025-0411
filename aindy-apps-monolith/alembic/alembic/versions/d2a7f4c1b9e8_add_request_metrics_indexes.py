"""add request metrics indexes

Revision ID: d2a7f4c1b9e8
Revises: c4f2a9d1e7b3
Create Date: 2026-03-22
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "d2a7f4c1b9e8"
down_revision = "c4f2a9d1e7b3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_request_metrics_created_at",
        "request_metrics",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_request_metrics_path_created_at",
        "request_metrics",
        ["path", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_request_metrics_path_created_at", table_name="request_metrics")
    op.drop_index("ix_request_metrics_created_at", table_name="request_metrics")

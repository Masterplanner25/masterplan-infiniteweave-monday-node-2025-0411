"""agent run capability token and trust policy fields

Revision ID: e1f2a3b4c5d6
Revises: c9d8e7f6a5b4
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e1f2a3b4c5d6"
down_revision = "c9d8e7f6a5b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs",
        sa.Column("capability_token", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "agent_trust_settings",
        sa.Column(
            "allowed_auto_grant_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("agent_trust_settings", "allowed_auto_grant_tools")
    op.drop_column("agent_runs", "capability_token")

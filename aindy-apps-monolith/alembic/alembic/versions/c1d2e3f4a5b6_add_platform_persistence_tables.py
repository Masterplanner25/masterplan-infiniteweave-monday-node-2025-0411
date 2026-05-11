"""add_platform_persistence_tables

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-03-31

Adds three tables that give dynamic platform registrations restart
durability.  Previously all dynamic flows, nodes, and webhook subscriptions
lived only in memory and were lost on server restart.

  dynamic_flows         — flows registered via POST /platform/flows
  dynamic_nodes         — nodes registered via POST /platform/nodes/register
  webhook_subscriptions — subscriptions registered via POST /platform/webhooks

All three tables use soft-delete (is_active column) so the audit trail is
preserved when items are deleted via the platform API.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    # ── dynamic_flows ──────────────────────────────────────────────────────
    op.create_table(
        "dynamic_flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("definition_json", postgresql.JSON(), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index(
        "ix_dynamic_flows_name",
        "dynamic_flows",
        ["name"],
        unique=True,
    )

    # ── dynamic_nodes ──────────────────────────────────────────────────────
    op.create_table(
        "dynamic_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("handler_config", postgresql.JSON(), nullable=False),
        sa.Column("secret", sa.String(512), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=True),
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index(
        "ix_dynamic_nodes_name",
        "dynamic_nodes",
        ["name"],
        unique=True,
    )

    # ── webhook_subscriptions ──────────────────────────────────────────────
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(256), nullable=False),
        sa.Column("callback_url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(512), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index(
        "ix_webhook_subscriptions_event_type",
        "webhook_subscriptions",
        ["event_type"],
    )


def downgrade():
    op.drop_index("ix_webhook_subscriptions_event_type", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")

    op.drop_index("ix_dynamic_nodes_name", table_name="dynamic_nodes")
    op.drop_table("dynamic_nodes")

    op.drop_index("ix_dynamic_flows_name", table_name="dynamic_flows")
    op.drop_table("dynamic_flows")

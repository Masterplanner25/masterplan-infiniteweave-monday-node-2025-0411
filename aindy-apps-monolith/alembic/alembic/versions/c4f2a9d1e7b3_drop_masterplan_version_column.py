"""drop masterplan version column

Revision ID: c4f2a9d1e7b3
Revises: 23da8ebc43f1
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4f2a9d1e7b3"
down_revision = "23da8ebc43f1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_master_plans_version")
    with op.batch_alter_table("master_plans") as batch:
        batch.drop_column("version")


def downgrade():
    with op.batch_alter_table("master_plans") as batch:
        batch.add_column(sa.Column("version", sa.String(), nullable=True))
    op.create_index("ix_master_plans_version", "master_plans", ["version"], unique=False)

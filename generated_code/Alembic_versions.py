# alembic/versions/001_add_memory_persistence.py
"""
Alembic migration for memory persistence tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_add_memory_persistence'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create memory_nodes table
    op.create_table('memory_nodes',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tags', postgresql.JSON(), nullable=False),
        sa.Column('node_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', postgresql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create memory_links table
    op.create_table('memory_links',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('source_node_id', postgresql.UUID(), nullable=False),
        sa.Column('target_node_id', postgresql.UUID(), nullable=False),
        sa.Column('link_type', sa.String(length=50), nullable=False),
        sa.Column('strength', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_node_id'], ['memory_nodes.id'], ),
        sa.ForeignKeyConstraint(['target_node_id'], ['memory_nodes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for performance
    op.create_index('idx_memory_nodes_tags', 'memory_nodes', ['tags'], postgresql_using='gin')
    op.create_index('idx_memory_nodes_created', 'memory_nodes', ['created_at'])
    op.create_index('idx_memory_links_source', 'memory_links', ['source_node_id'])
    op.create_index('idx_memory_links_target', 'memory_links', ['target_node_id'])

def downgrade():
    op.drop_table('memory_links')
    op.drop_table('memory_nodes')
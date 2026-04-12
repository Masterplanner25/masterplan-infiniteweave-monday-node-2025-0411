"""create missing tables: tasks, analysis_results, code_generations

Revision ID: d1a2b3c4d5e6
Revises: 492fc82e3e2b
Create Date: 2026-03-18 01:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'd1a2b3c4d5e6'
down_revision: Union[str, None] = '492fc82e3e2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {r[0] for r in conn.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    ))}

    if 'tasks' not in existing:
        op.create_table('tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('priority', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('scheduled_time', sa.DateTime(), nullable=True),
        sa.Column('reminder_time', sa.DateTime(), nullable=True),
        sa.Column('recurrence', sa.String(), nullable=True),
        sa.Column('time_spent', sa.Float(), nullable=True),
        sa.Column('task_complexity', sa.Integer(), nullable=True),
        sa.Column('skill_level', sa.Integer(), nullable=True),
        sa.Column('ai_utilization', sa.Integer(), nullable=True),
        sa.Column('task_difficulty', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_tasks_id'), 'tasks', ['id'], unique=False)
        op.create_index(op.f('ix_tasks_name'), 'tasks', ['name'], unique=False)

    if 'analysis_results' not in existing:
        op.create_table('analysis_results',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('file_type', sa.String(), nullable=True),
        sa.Column('analysis_type', sa.String(), nullable=True),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('execution_seconds', sa.Float(), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('result_full', sa.Text(), nullable=True),
        sa.Column('task_priority', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_analysis_results_session_id'), 'analysis_results', ['session_id'], unique=False)
        op.create_index(op.f('ix_analysis_results_user_id'), 'analysis_results', ['user_id'], unique=False)

    if 'code_generations' not in existing:
        op.create_table('code_generations',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('analysis_id', UUID(as_uuid=True), sa.ForeignKey('analysis_results.id', ondelete='SET NULL'), nullable=True),
        sa.Column('generation_type', sa.String(), nullable=True),
        sa.Column('original_code', sa.Text(), nullable=True),
        sa.Column('generated_code', sa.Text(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('execution_seconds', sa.Float(), nullable=True),
        sa.Column('quality_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_code_generations_session_id'), 'code_generations', ['session_id'], unique=False)
        op.create_index(op.f('ix_code_generations_user_id'), 'code_generations', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_code_generations_user_id'), table_name='code_generations')
    op.drop_index(op.f('ix_code_generations_session_id'), table_name='code_generations')
    op.drop_table('code_generations')
    op.drop_index(op.f('ix_analysis_results_user_id'), table_name='analysis_results')
    op.drop_index(op.f('ix_analysis_results_session_id'), table_name='analysis_results')
    op.drop_table('analysis_results')
    op.drop_index(op.f('ix_tasks_name'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_id'), table_name='tasks')
    op.drop_table('tasks')

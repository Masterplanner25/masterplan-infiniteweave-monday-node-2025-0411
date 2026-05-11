"""normalize remaining user ids to uuid

Revision ID: f7a8b9c0d1e2
Revises: f2a3b4c5d6e7
Create Date: 2026-03-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UUID_REGEX = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(col.get("name") == column_name for col in columns)


def _sanitize_uuid_text(table_name: str, column_name: str) -> None:
    if not _has_column(table_name, column_name):
        return
    op.execute(
        f"""
        UPDATE {table_name}
        SET {column_name} = NULL
        WHERE {column_name} IS NOT NULL
          AND {column_name}::text !~* '{UUID_REGEX}';
        """
    )


def _alter_to_uuid(table_name: str, column_name: str, nullable: bool) -> None:
    if not _has_column(table_name, column_name):
        return
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.String(),
        type_=postgresql.UUID(as_uuid=True),
        nullable=nullable,
        postgresql_using=f"{column_name}::uuid",
    )


def _add_fk(table_name: str, column_name: str, constraint_name: str) -> None:
    if not _has_column(table_name, column_name):
        return
    op.create_foreign_key(
        constraint_name,
        table_name,
        "users",
        [column_name],
        ["id"],
    )


def upgrade() -> None:
    nullable_columns = [
        ("agent_events", "user_id", "fk_agent_events_user_id"),
        ("agents", "owner_user_id", "fk_agents_owner_user_id"),
        ("automation_logs", "user_id", "fk_automation_logs_user_id"),
        ("calculation_results", "user_id", "fk_calculation_results_user_id"),
        ("event_outcomes", "user_id", "fk_event_outcomes_user_id"),
        ("flow_runs", "user_id", "fk_flow_runs_user_id"),
        ("loop_adjustments", "user_id", "fk_loop_adjustments_user_id"),
        ("master_plans", "user_id", "fk_master_plans_user_id"),
        ("memory_metrics", "user_id", "fk_memory_metrics_user_id"),
        ("memory_nodes", "user_id", "fk_memory_nodes_user_id"),
        ("memory_traces", "user_id", "fk_memory_traces_user_id"),
        ("request_metrics", "user_id", "fk_request_metrics_user_id"),
        ("strategies", "user_id", "fk_strategies_user_id"),
        ("watcher_signals", "user_id", "fk_watcher_signals_user_id"),
    ]
    required_columns = [
        ("agent_runs", "user_id", "fk_agent_runs_user_id"),
        ("agent_trust_settings", "user_id", "fk_agent_trust_settings_user_id"),
        ("analysis_results", "user_id", "fk_analysis_results_user_id"),
        ("code_generations", "user_id", "fk_code_generations_user_id"),
        ("score_history", "user_id", "fk_score_history_user_id"),
        ("user_feedback", "user_id", "fk_user_feedback_user_id"),
        ("user_scores", "user_id", "fk_user_scores_user_id"),
    ]

    for table_name, column_name, _ in nullable_columns + required_columns:
        _sanitize_uuid_text(table_name, column_name)

    for table_name, column_name, constraint_name in nullable_columns:
        _alter_to_uuid(table_name, column_name, nullable=True)
        _add_fk(table_name, column_name, constraint_name)

    for table_name, column_name, constraint_name in required_columns:
        _alter_to_uuid(table_name, column_name, nullable=True)
        if _has_column(table_name, column_name):
            op.execute(f"DELETE FROM {table_name} WHERE {column_name} IS NULL;")
            op.alter_column(table_name, column_name, nullable=False)
            _add_fk(table_name, column_name, constraint_name)

def downgrade() -> None:
    all_columns = [
        ("agent_events", "user_id", "fk_agent_events_user_id", True),
        ("agents", "owner_user_id", "fk_agents_owner_user_id", True),
        ("automation_logs", "user_id", "fk_automation_logs_user_id", True),
        ("calculation_results", "user_id", "fk_calculation_results_user_id", True),
        ("event_outcomes", "user_id", "fk_event_outcomes_user_id", True),
        ("flow_runs", "user_id", "fk_flow_runs_user_id", True),
        ("loop_adjustments", "user_id", "fk_loop_adjustments_user_id", True),
        ("master_plans", "user_id", "fk_master_plans_user_id", True),
        ("memory_metrics", "user_id", "fk_memory_metrics_user_id", True),
        ("memory_nodes", "user_id", "fk_memory_nodes_user_id", True),
        ("memory_traces", "user_id", "fk_memory_traces_user_id", True),
        ("request_metrics", "user_id", "fk_request_metrics_user_id", True),
        ("strategies", "user_id", "fk_strategies_user_id", True),
        ("watcher_signals", "user_id", "fk_watcher_signals_user_id", True),
        ("agent_runs", "user_id", "fk_agent_runs_user_id", False),
        ("agent_trust_settings", "user_id", "fk_agent_trust_settings_user_id", False),
        ("analysis_results", "user_id", "fk_analysis_results_user_id", False),
        ("code_generations", "user_id", "fk_code_generations_user_id", False),
        ("score_history", "user_id", "fk_score_history_user_id", False),
        ("user_feedback", "user_id", "fk_user_feedback_user_id", False),
        ("user_scores", "user_id", "fk_user_scores_user_id", False),
    ]

    for table_name, column_name, constraint_name, nullable in all_columns:
        if _has_column(table_name, column_name):
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")
            op.alter_column(
                table_name,
                column_name,
                existing_type=postgresql.UUID(as_uuid=True),
                type_=sa.String(),
                nullable=nullable,
                postgresql_using=f"{column_name}::text",
            )

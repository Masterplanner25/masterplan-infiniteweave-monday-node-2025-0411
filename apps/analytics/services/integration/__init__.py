"""Cross-domain adapters used by analytics orchestration."""

from . import dependency_adapter, masterplan_guard, tasks_bridge
from .dependency_adapter import (
    create_loop_adjustment,
    fetch_memory_signals,
    fetch_next_ready_task,
    fetch_recent_memory,
    fetch_social_performance_signals,
    fetch_system_state,
    fetch_task_graph_context,
    fetch_user_metrics,
    get_latest_loop_adjustment,
    get_latest_loop_adjustment_for_update,
    get_pending_loop_adjustment,
    list_incomplete_tasks,
    list_recent_feedback_rows,
    list_strategy_accuracy_adjustments,
    update_loop_adjustment,
)
from .masterplan_guard import assert_masterplan_owned_via_syscall
from .tasks_bridge import get_task_graph_context_via_syscall

__all__ = [
    "assert_masterplan_owned_via_syscall",
    "create_loop_adjustment",
    "dependency_adapter",
    "fetch_memory_signals",
    "fetch_next_ready_task",
    "fetch_recent_memory",
    "fetch_social_performance_signals",
    "fetch_system_state",
    "fetch_task_graph_context",
    "fetch_user_metrics",
    "get_latest_loop_adjustment",
    "get_latest_loop_adjustment_for_update",
    "get_pending_loop_adjustment",
    "get_task_graph_context_via_syscall",
    "list_incomplete_tasks",
    "list_recent_feedback_rows",
    "list_strategy_accuracy_adjustments",
    "masterplan_guard",
    "tasks_bridge",
    "update_loop_adjustment",
]

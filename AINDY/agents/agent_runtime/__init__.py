import sys

from AINDY.agents.agent_runtime.approvals import approve_run, reject_run
from AINDY.agents.agent_runtime.creation import _create_run_from_plan, create_run
from AINDY.agents.agent_runtime.execution import _build_execution_memory_context, execute_run
from AINDY.agents.agent_runtime.planning import (
    PLANNER_SYSTEM_PROMPT,
    _build_kpi_context_block,
    _legacy_planner_context_block_disabled,
    _requires_approval,
    generate_plan,
)
from AINDY.agents.agent_runtime.presentation import (
    _normalize_agent_events,
    _run_to_dict,
    get_run_events,
    run_to_dict,
    to_execution_response,
)
from AINDY.agents.agent_runtime.replay import replay_run
from AINDY.agents.agent_runtime.shared import (
    LOCAL_AGENT_ID,
    _OBJECTIVE_ATTR,
    _OBJECTIVE_PREVIEW_KEY,
    _client,
    _db_run_id,
    _db_user_id,
    _emit_runtime_event,
    _get_client,
    _get_planner_context,
    _get_tools_for_run,
    _objective_preview,
    _plan_failure,
    _resolve_objective,
    _run_objective,
    _user_matches,
    chat_completion,
    logger,
    perform_external_call,
)
from AINDY.core.system_event_service import emit_error_event

sys.modules["AINDY.agents.agent_runtime"] = sys.modules[__name__]
sys.modules["agents.agent_runtime"] = sys.modules[__name__]

__all__ = [
    "LOCAL_AGENT_ID",
    "PLANNER_SYSTEM_PROMPT",
    "_OBJECTIVE_ATTR",
    "_OBJECTIVE_PREVIEW_KEY",
    "_build_execution_memory_context",
    "_build_kpi_context_block",
    "_client",
    "_create_run_from_plan",
    "_db_run_id",
    "_db_user_id",
    "_emit_runtime_event",
    "_get_client",
    "_get_planner_context",
    "_get_tools_for_run",
    "_legacy_planner_context_block_disabled",
    "_normalize_agent_events",
    "_objective_preview",
    "_plan_failure",
    "_requires_approval",
    "_resolve_objective",
    "_run_objective",
    "_run_to_dict",
    "_user_matches",
    "approve_run",
    "chat_completion",
    "create_run",
    "emit_error_event",
    "execute_run",
    "generate_plan",
    "get_run_events",
    "logger",
    "perform_external_call",
    "reject_run",
    "replay_run",
    "run_to_dict",
    "to_execution_response",
]

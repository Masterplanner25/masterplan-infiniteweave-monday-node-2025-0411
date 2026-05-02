"""Compatibility wrapper for the runtime-owned agent router."""

from AINDY.routes.agent_router import (  # noqa: F401
    RunRequest,
    TrustSettingsUpdate,
    _current_user_id,
    _execute_agent,
    _run_to_response,
    _with_legacy_log_alias,
    approve_agent_run,
    create_agent_run,
    get_agent_run,
    get_run_events,
    get_run_steps,
    get_tool_suggestions,
    get_trust_settings,
    list_agent_runs,
    list_tools,
    recover_agent_run,
    reject_agent_run,
    replay_agent_run,
    router,
    update_trust_settings,
)
from AINDY.core.execution_helper import execute_with_pipeline_sync  # noqa: F401
from AINDY.db.database import get_db  # noqa: F401

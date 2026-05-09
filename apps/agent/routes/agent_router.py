"""Deprecated compatibility wrapper for the runtime-owned agent router.

Prefer importing from ``AINDY.routes.agent_router`` directly. This module
remains only as a transitional re-export for legacy callers and intentionally
exposes only the public router surface.
"""

import AINDY.routes.agent_router as _runtime_agent_router

RunRequest = _runtime_agent_router.RunRequest
TrustSettingsUpdate = _runtime_agent_router.TrustSettingsUpdate
approve_agent_run = _runtime_agent_router.approve_agent_run
create_agent_run = _runtime_agent_router.create_agent_run
get_agent_run = _runtime_agent_router.get_agent_run
get_run_events = _runtime_agent_router.get_run_events
get_run_steps = _runtime_agent_router.get_run_steps
get_tool_suggestions = _runtime_agent_router.get_tool_suggestions
get_trust_settings = _runtime_agent_router.get_trust_settings
list_agent_runs = _runtime_agent_router.list_agent_runs
list_tools = _runtime_agent_router.list_tools
recover_agent_run = _runtime_agent_router.recover_agent_run
reject_agent_run = _runtime_agent_router.reject_agent_run
replay_agent_run = _runtime_agent_router.replay_agent_run
router = _runtime_agent_router.router
update_trust_settings = _runtime_agent_router.update_trust_settings

"""Generic agent tool registry and execution boundary."""

from __future__ import annotations

import logging
from typing import Callable

from AINDY.core.execution_signal_helper import queue_system_event

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, dict] = {}
_SUGGESTION_PROVIDERS: list[Callable] = []
_LOADING_PLUGINS = False


def _ensure_tools_loaded() -> None:
    global _LOADING_PLUGINS
    if _LOADING_PLUGINS:
        return
    _LOADING_PLUGINS = True
    try:
        from AINDY.platform_layer.registry import load_plugins

        load_plugins()
    except Exception as exc:
        logger.debug("agent tool plugin load skipped: %s", exc)
    finally:
        _LOADING_PLUGINS = False


def register_tool(
    name: str,
    risk: str,
    description: str,
    capability: str,
    required_capability: str,
    category: str,
    egress_scope: str,
):
    """Register an agent tool implementation with platform metadata."""
    def wrapper(fn: Callable) -> Callable:
        TOOL_REGISTRY[name] = {
            "fn": fn,
            "risk": risk,
            "description": description,
            "capability": capability,
            "required_capability": required_capability,
            "category": category,
            "egress_scope": egress_scope,
        }
        return fn

    return wrapper


def register_tool_suggestion_provider(provider: Callable) -> Callable:
    """Register a callable that can suggest tools for a context snapshot."""
    if provider not in _SUGGESTION_PROVIDERS:
        _SUGGESTION_PROVIDERS.append(provider)
    return provider


def execute_tool(
    tool_name: str,
    args: dict,
    user_id: str,
    db,
    run_id: str = None,
    execution_token: dict = None,
) -> dict:
    """Execute a registered tool by name and return a normalized result."""
    _ensure_tools_loaded()
    entry = TOOL_REGISTRY.get(tool_name)
    if not entry:
        return {
            "success": False,
            "result": None,
            "error": f"Tool '{tool_name}' not found in registry",
        }
    if run_id and execution_token is None:
        return {
            "success": False,
            "result": None,
            "error": "capability token is required for agent run tool execution",
        }
    if execution_token is not None:
        if not run_id:
            return {
                "success": False,
                "result": None,
                "error": "run_id is required when execution_token is supplied",
            }
        try:
            from AINDY.agents.capability_service import check_tool_capability

            capability_check = check_tool_capability(
                token=execution_token,
                run_id=run_id,
                user_id=user_id,
                tool_name=tool_name,
            )
            if not capability_check["ok"]:
                queue_system_event(
                    db=db,
                    event_type="capability.denied",
                    user_id=user_id,
                    trace_id=str(run_id),
                    payload={
                        "run_id": str(run_id),
                        "tool_name": tool_name,
                        "error": capability_check["error"],
                        "allowed_capabilities": capability_check.get("allowed_capabilities", []),
                        "granted_tools": capability_check.get("granted_tools", []),
                    },
                    required=True,
                )
                return {
                    "success": False,
                    "result": None,
                    "error": capability_check["error"],
                }
            queue_system_event(
                db=db,
                event_type="capability.allowed",
                user_id=user_id,
                trace_id=str(run_id),
                payload={
                    "run_id": str(run_id),
                    "tool_name": tool_name,
                    "allowed_capabilities": capability_check.get("allowed_capabilities", []),
                    "granted_tools": capability_check.get("granted_tools", []),
                },
                required=True,
            )
        except Exception as exc:
            logger.warning("[AgentTool] %s capability check failed: %s", tool_name, exc)
            return {
                "success": False,
                "result": None,
                "error": "capability enforcement failed",
            }
    try:
        result = entry["fn"](args=args, user_id=user_id, db=db)
        return {"success": True, "result": result, "error": None}
    except Exception as exc:
        logger.warning("[AgentTool] %s failed: %s", tool_name, exc)
        return {"success": False, "result": None, "error": str(exc)}


def get_tool_risk(tool_name: str) -> str:
    """Return risk level of a registered tool, or 'high' if unknown."""
    _ensure_tools_loaded()
    entry = TOOL_REGISTRY.get(tool_name)
    return entry["risk"] if entry else "high"


def suggest_tools(kpi_snapshot: dict, user_id: str = None, db=None) -> list:
    """Return tool suggestions from registered app-owned providers."""
    _ensure_tools_loaded()
    for provider in tuple(_SUGGESTION_PROVIDERS):
        try:
            suggestions = provider(kpi_snapshot=kpi_snapshot, user_id=user_id, db=db)
        except Exception as exc:
            logger.warning("[AgentTools] suggestion provider failed: %s", exc)
            continue
        if suggestions:
            return suggestions[:3]
    return []

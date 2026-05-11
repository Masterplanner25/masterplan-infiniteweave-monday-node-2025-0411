"""App-owned generic agent tools registered through runtime-owned registries."""

from __future__ import annotations

import logging

from AINDY.agents.tool_registry import TOOL_REGISTRY, register_tool, register_tool_suggestion_provider
from AINDY.agents.tool_syscalls import invoke_tool_syscall
from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool

logger = logging.getLogger(__name__)


def register() -> None:
    register_tool(
        "memory.recall",
        risk="low",
        description="Recall relevant memory nodes for a given query",
        capability="tool:memory.recall",
        required_capability="read_memory",
        category="memory",
        egress_scope="internal",
    )(memory_recall)
    register_tool(
        "memory.write",
        risk="low",
        description="Write a memory node with content and tags",
        capability="tool:memory.write",
        required_capability="write_memory",
        category="memory",
        egress_scope="internal",
    )(memory_write)
    register_tool_suggestion_provider(suggest_tools_for_kpi)


def memory_recall(args: dict, user_id: str, db) -> dict:
    return invoke_tool_syscall("sys.v1.memory.read", args, user_id=user_id, capability="memory.read")


def memory_write(args: dict, user_id: str, db) -> dict:
    payload = {"source": "agent", **args}
    data = invoke_tool_syscall("sys.v1.memory.write", payload, user_id=user_id, capability="memory.write")
    node = data.get("node", {})
    return {"node_id": node.get("id") if isinstance(node, dict) else None}


def _load_suggestion_context(
    suggestion_context: dict | None,
    *,
    user_id: str | None,
    db,
) -> dict | None:
    if isinstance(suggestion_context, dict) and suggestion_context:
        return suggestion_context
    if not user_id or db is None:
        return suggestion_context if isinstance(suggestion_context, dict) else None
    try:
        from AINDY.platform_layer.registry import get_job

        get_user_kpi_snapshot = get_job("analytics.kpi_snapshot")
        if get_user_kpi_snapshot is None:
            return suggestion_context if isinstance(suggestion_context, dict) else None
        snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
        return snapshot if isinstance(snapshot, dict) else None
    except Exception as exc:
        logger.warning("[AgentTools] suggestion context lookup failed: %s", exc)
        return suggestion_context if isinstance(suggestion_context, dict) else None


def suggest_tools_for_kpi(
    suggestion_context: dict | None = None,
    user_id: str = None,
    db=None,
    **legacy_kwargs,
) -> list:
    kpi_snapshot = _load_suggestion_context(
        suggestion_context if suggestion_context is not None else legacy_kwargs.get("kpi_snapshot"),
        user_id=user_id,
        db=db,
    )
    try:
        ctx = make_syscall_ctx_from_tool(str(user_id or ""), capabilities=["agent.suggest_tools"])
        result = get_dispatcher().dispatch(
            "sys.v1.agent.suggest_tools",
            {"kpi_snapshot": kpi_snapshot},
            ctx,
        )
        if result["status"] == "success":
            suggestions = result["data"].get("suggestions", [])
            if suggestions:
                return suggestions
    except Exception as exc:
        logger.warning("[AgentTools] suggest_tools dispatch failed: %s", exc)

    if user_id and db is not None:
        try:
            from AINDY.platform_layer.registry import get_job

            get_latest_adjustment = get_job("analytics.latest_adjustment")
            latest = get_latest_adjustment(user_id=user_id, db=db) if get_latest_adjustment else None
            payload = getattr(latest, "adjustment_payload", {}) if latest is not None else {}
            if not isinstance(payload, dict):
                payload = {}
            persisted_suggestions = payload.get("suggestions", [])
            if not isinstance(persisted_suggestions, list):
                persisted_suggestions = []
            if persisted_suggestions:
                return persisted_suggestions[:3]
        except Exception as exc:
            logger.warning("[AgentTools] latest adjustment lookup failed: %s", exc)

    if not kpi_snapshot:
        return []

    try:
        focus = float(kpi_snapshot.get("focus_quality", 50.0) or 50.0)
        speed = float(kpi_snapshot.get("execution_speed", 50.0) or 50.0)
        ai_boost = float(kpi_snapshot.get("ai_productivity_boost", 50.0) or 50.0)
        master = float(kpi_snapshot.get("master_score", 50.0) or 50.0)
    except (TypeError, ValueError):
        return []

    def _first_tool_by_category(category: str) -> str | None:
        for name, entry in TOOL_REGISTRY.items():
            if entry.get("category") == category:
                return name
        return None

    suggestions: list[dict] = []

    if focus < 40:
        tool = _first_tool_by_category("memory")
        if tool:
            suggestions.append({
                "tool": tool,
                "reason": f"Focus quality is low ({focus:.0f}/100) - recall past context before starting new work",
                "suggested_goal": "Recall recent memories and notes to regain context on current priorities",
            })

    if speed < 55 and len(suggestions) < 3:
        tool = _first_tool_by_category("task")
        if tool:
            reason = (
                f"Execution speed is low ({speed:.0f}/100) - create a concrete next action to rebuild momentum"
                if speed < 40
                else f"Execution pace is below average ({speed:.0f}/100) - a new task could help"
            )
            suggestions.append({
                "tool": tool,
                "reason": reason,
                "suggested_goal": "Create a focused task for the most important thing I need to do today",
            })

    if ai_boost < 40 and len(suggestions) < 3:
        tool = _first_tool_by_category("analysis")
        if tool:
            suggestions.append({
                "tool": tool,
                "reason": f"ARM usage is low ({ai_boost:.0f}/100) - analyzing code could boost quality scores",
                "suggested_goal": "Analyze the current codebase for architecture and integrity improvements",
            })

    if master >= 70 and len(suggestions) < 3:
        tool = _first_tool_by_category("planning")
        if tool:
            suggestions.append({
                "tool": tool,
                "reason": f"Strong overall performance ({master:.0f}/100) - review strategic direction",
                "suggested_goal": "Review current MasterPlan progress and refine next priorities",
            })

    return suggestions[:3]

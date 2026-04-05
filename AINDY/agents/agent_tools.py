"""
Agent Tool Registry — Sprint N+4 Agentics Phase 1+2

Wraps A.I.N.D.Y. services into callable, auditable tool functions.

Each tool returns:
    {"success": bool, "result": any, "error": str | None}

Risk classification (hardcoded invariant):
    low    — read-only or additive-only operations
    medium — external API calls, writes with cost (credits), or state changes
    high   — mutates long-term planning state (genesis, locked plans)

Registration:
    @register_tool(
        "name",
        risk="low|medium|high",
        description="...",
        capability="tool:name",
        required_capability="capability_name",
        category="...",
        egress_scope="none|internal|external_*",
    )
    def my_tool(args: dict, user_id: str, db) -> dict: ...

The TOOL_REGISTRY dict maps tool_name →
{fn, risk, description, capability, required_capability, category, egress_scope}.
"""
import logging
from typing import Callable

from core.execution_signal_helper import queue_system_event
from kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool

logger = logging.getLogger(__name__)


def _syscall(name: str, payload: dict, user_id: str, capability: str) -> dict:
    """Dispatch a syscall from within a tool and unwrap the response.

    Returns the ``data`` dict on success, or raises RuntimeError on error.
    This preserves the tool's original return contract (raw domain data).
    """
    ctx = make_syscall_ctx_from_tool(user_id, capabilities=[capability])
    result = get_dispatcher().dispatch(name, payload, ctx)
    if result["status"] == "error":
        raise RuntimeError(result["error"])
    return result["data"]

# ── Registry ─────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, dict] = {}


def register_tool(
    name: str,
    risk: str,
    description: str,
    capability: str,
    required_capability: str,
    category: str,
    egress_scope: str,
):
    """
    Decorator to register an agent tool.

    Usage:
        @register_tool(
            "task.create",
            risk="low",
            description="Create a new task",
            capability="tool:task.create",
            required_capability="manage_tasks",
            category="task",
            egress_scope="internal",
        )
        def task_create(args: dict, user_id: str, db) -> dict:
            ...
    """
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


def execute_tool(
    tool_name: str,
    args: dict,
    user_id: str,
    db,
    run_id: str = None,
    execution_token: dict = None,
) -> dict:
    """
    Execute a registered tool by name.

    Returns {"success": bool, "result": any, "error": str | None}.
    Never raises — wraps all exceptions.
    """
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
            from agents.capability_service import check_tool_capability

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
    entry = TOOL_REGISTRY.get(tool_name)
    return entry["risk"] if entry else "high"


def suggest_tools(kpi_snapshot: dict, user_id: str = None, db=None) -> list:
    """
    Return up to 3 tool suggestions based on the user's current KPI state.

    Routes through sys.v1.agent.suggest_tools syscall handler.
    Returns [] on any failure. Never raises.
    """
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

    if not kpi_snapshot:
        return []

    try:
        suggestions: list[dict] = []
        focus = float(kpi_snapshot.get("focus_quality", 50.0) or 50.0)
        speed = float(kpi_snapshot.get("execution_speed", 50.0) or 50.0)
        ai_boost = float(kpi_snapshot.get("ai_productivity_boost", 50.0) or 50.0)
        master = float(kpi_snapshot.get("master_score", 50.0) or 50.0)
    except (TypeError, ValueError):
        return []

    if focus < 40:
        suggestions.append({
            "tool": "memory.recall",
            "reason": f"Focus quality is low ({focus:.0f}/100) - recall past context before starting new work",
            "suggested_goal": "Recall recent memories and notes to regain context on current priorities",
        })

    if speed < 40:
        suggestions.append({
            "tool": "task.create",
            "reason": f"Execution speed is low ({speed:.0f}/100) - create a concrete next action to rebuild momentum",
            "suggested_goal": "Create a focused task for the most important thing I need to do today",
        })
    elif speed < 55:
        suggestions.append({
            "tool": "task.create",
            "reason": f"Execution pace is below average ({speed:.0f}/100) - a new task could help",
            "suggested_goal": "Create a small, completable task to get back on track",
        })

    if ai_boost < 40 and len(suggestions) < 3:
        suggestions.append({
            "tool": "arm.analyze",
            "reason": f"ARM usage is low ({ai_boost:.0f}/100) - analyzing code could boost quality scores",
            "suggested_goal": "Analyze the current codebase for architecture and integrity improvements",
        })

    if master >= 70 and len(suggestions) < 3:
        suggestions.append({
            "tool": "genesis.message",
            "reason": f"Strong overall performance ({master:.0f}/100) - review strategic direction with Genesis",
            "suggested_goal": "Review my current MasterPlan progress and refine next priorities with Genesis",
        })

    return suggestions[:3]


# ── Tool Implementations ─────────────────────────────────────────────────────


@register_tool(
    "task.create",
    risk="low",
    description="Create a new task in the user's task list",
    capability="tool:task.create",
    required_capability="manage_tasks",
    category="task",
    egress_scope="internal",
)
def task_create(args: dict, user_id: str, db) -> dict:
    data = _syscall("sys.v1.task.create", args, user_id, "task.create")
    return {"task_id": data.get("task_id"), "name": data.get("task_name"), "status": data.get("status")}


@register_tool(
    "task.complete",
    risk="medium",
    description="Mark a task as complete by name",
    capability="tool:task.complete",
    required_capability="manage_tasks",
    category="task",
    egress_scope="internal",
)
def task_complete(args: dict, user_id: str, db) -> dict:
    return _syscall("sys.v1.task.complete_full", args, user_id, "task.complete_full")


@register_tool(
    "memory.recall",
    risk="low",
    description="Recall relevant memory nodes for a given query",
    capability="tool:memory.recall",
    required_capability="read_memory",
    category="memory",
    egress_scope="internal",
)
def memory_recall(args: dict, user_id: str, db) -> dict:
    return _syscall("sys.v1.memory.read", args, user_id, "memory.read")


@register_tool(
    "memory.write",
    risk="low",
    description="Write a memory node with content and tags",
    capability="tool:memory.write",
    required_capability="write_memory",
    category="memory",
    egress_scope="internal",
)
def memory_write(args: dict, user_id: str, db) -> dict:
    # Ensure "source" defaults to "agent" (preserved from original behavior)
    payload = {"source": "agent", **args}
    data = _syscall("sys.v1.memory.write", payload, user_id, "memory.write")
    node = data.get("node", {})
    return {"node_id": node.get("id") if isinstance(node, dict) else None}


@register_tool(
    "arm.analyze",
    risk="medium",
    description="Analyze code or a topic using the ARM reasoning engine",
    capability="tool:arm.analyze",
    required_capability="external_api_call",
    category="arm",
    egress_scope="external_llm",
)
def arm_analyze(args: dict, user_id: str, db) -> dict:
    data = _syscall("sys.v1.arm.analyze", args, user_id, "arm.analyze")
    return {
        "summary": data.get("summary", ""),
        "architecture_score": data.get("architecture_score"),
        "integrity_score": data.get("integrity_score"),
        "analysis_id": data.get("analysis_id"),
    }


@register_tool(
    "arm.generate",
    risk="medium",
    description="Generate or refactor code using the ARM code generation engine",
    capability="tool:arm.generate",
    required_capability="external_api_call",
    category="arm",
    egress_scope="external_llm",
)
def arm_generate(args: dict, user_id: str, db) -> dict:
    data = _syscall("sys.v1.arm.generate", args, user_id, "arm.generate")
    return {
        "generated_code": data.get("generated_code", ""),
        "explanation": data.get("explanation", ""),
        "generation_id": data.get("generation_id"),
    }


@register_tool(
    "leadgen.search",
    risk="medium",
    description="Search for B2B leads matching a query",
    capability="tool:leadgen.search",
    required_capability="external_api_call",
    category="leadgen",
    egress_scope="external_web",
)
def leadgen_search(args: dict, user_id: str, db) -> dict:
    data = _syscall("sys.v1.leadgen.search_ai", args, user_id, "leadgen.search_ai")
    return {"leads": data.get("leads", []), "count": data.get("count", 0)}


@register_tool(
    "research.query",
    risk="low",
    description="Query external sources for research on a topic",
    capability="tool:research.query",
    required_capability="external_api_call",
    category="research",
    egress_scope="external_web",
)
def research_query(args: dict, user_id: str, db) -> dict:
    return _syscall("sys.v1.research.query", args, user_id, "research.query")


@register_tool(
    "genesis.message",
    risk="high",
    description="Send a message to the Genesis strategic planning session (modifies MasterPlan state)",
    capability="tool:genesis.message",
    required_capability="strategic_planning",
    category="genesis",
    egress_scope="external_llm",
)
def genesis_message(args: dict, user_id: str, db) -> dict:
    return _syscall("sys.v1.genesis.message", args, user_id, "genesis.message")

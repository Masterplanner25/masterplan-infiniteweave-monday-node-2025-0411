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

from services.system_event_service import emit_system_event

logger = logging.getLogger(__name__)

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
            from services.capability_service import check_tool_capability

            capability_check = check_tool_capability(
                token=execution_token,
                run_id=run_id,
                user_id=user_id,
                tool_name=tool_name,
            )
            if not capability_check["ok"]:
                emit_system_event(
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
            emit_system_event(
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

    Each suggestion: {tool, reason, suggested_goal}

    Rules (in priority order):
      focus_quality < 40   → memory.recall   (recall context before deep work)
      execution_speed < 40 → task.create     (rebuild momentum with a concrete task)
      ai_boost < 40        → arm.analyze     (improve code quality via ARM)
      task_velocity low    → task.create     (secondary trigger if speed between 40-55)
      master_score >= 70   → genesis.message (high performer unlock)

    Returns [] when kpi_snapshot is None/empty or no rules trigger.
    Never raises.
    """
    if user_id and db:
        try:
            from services.infinity_loop import get_latest_adjustment

            latest = get_latest_adjustment(user_id=user_id, db=db)
            if latest and latest.adjustment_payload:
                persisted = latest.adjustment_payload.get("suggestions")
                if isinstance(persisted, list):
                    return persisted[:3]
        except Exception as exc:
            logger.warning("[AgentTools] persisted suggestions lookup failed: %s", exc)

    if not kpi_snapshot:
        return []

    try:
        suggestions = []

        focus = kpi_snapshot.get("focus_quality", 50.0)
        speed = kpi_snapshot.get("execution_speed", 50.0)
        ai_boost = kpi_snapshot.get("ai_productivity_boost", 50.0)
        master = kpi_snapshot.get("master_score", 50.0)

        if focus < 40:
            suggestions.append({
                "tool": "memory.recall",
                "reason": f"Focus quality is low ({focus:.0f}/100) — recall past context before starting new work",
                "suggested_goal": "Recall recent memories and notes to regain context on current priorities",
            })

        if speed < 40:
            suggestions.append({
                "tool": "task.create",
                "reason": f"Execution speed is low ({speed:.0f}/100) — create a concrete next action to rebuild momentum",
                "suggested_goal": "Create a focused task for the most important thing I need to do today",
            })
        elif speed < 55:
            suggestions.append({
                "tool": "task.create",
                "reason": f"Execution pace is below average ({speed:.0f}/100) — a new task could help",
                "suggested_goal": "Create a small, completable task to get back on track",
            })

        if ai_boost < 40 and len(suggestions) < 3:
            suggestions.append({
                "tool": "arm.analyze",
                "reason": f"ARM usage is low ({ai_boost:.0f}/100) — analyzing code could boost quality scores",
                "suggested_goal": "Analyze the current codebase for architecture and integrity improvements",
            })

        if master >= 70 and len(suggestions) < 3:
            suggestions.append({
                "tool": "genesis.message",
                "reason": f"Strong overall performance ({master:.0f}/100) — review strategic direction with Genesis",
                "suggested_goal": "Review my current MasterPlan progress and refine next priorities with Genesis",
            })

        return suggestions[:3]

    except Exception as exc:
        logger.warning("[AgentTools] suggest_tools failed: %s", exc)
        return []


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
    from services.task_services import create_task

    name = args.get("name") or args.get("task_name")
    if not name:
        raise ValueError("task.create requires 'name'")

    task = create_task(
        db=db,
        name=name,
        category=args.get("category", "general"),
        priority=args.get("priority", "medium"),
        due_date=args.get("due_date"),
        user_id=user_id,
    )
    return {"task_id": str(task.id), "name": task.name, "status": task.status}


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
    from services.task_services import execute_task_completion

    name = args.get("name") or args.get("task_name")
    if not name:
        raise ValueError("task.complete requires 'name'")

    return execute_task_completion(db=db, name=name, user_id=user_id)


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
    from bridge.bridge import recall_memories

    query = args.get("query", "")
    tags = args.get("tags", [])
    limit = int(args.get("limit", 5))

    nodes = recall_memories(
        query=query,
        tags=tags,
        limit=limit,
        user_id=user_id,
        db=db,
    )
    return {"nodes": nodes, "count": len(nodes)}


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
    from bridge.bridge import create_memory_node

    content = args.get("content")
    if not content:
        raise ValueError("memory.write requires 'content'")

    node = create_memory_node(
        content=content,
        source=args.get("source", "agent"),
        tags=args.get("tags", []),
        user_id=user_id,
        db=db,
        node_type=args.get("node_type"),
    )
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
    from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    # For agent-driven analysis, we wrap the prompt as additional_context
    # and use a sentinel path (the analyzer reads from the path, so we
    # require either a real file_path or accept failure gracefully).
    file_path = args.get("file_path")
    if not file_path:
        raise ValueError("arm.analyze requires 'file_path'")

    analyzer = DeepSeekCodeAnalyzer()
    result = analyzer.run_analysis(
        file_path=file_path,
        user_id=user_id,
        db=db,
        additional_context=args.get("additional_context", ""),
    )
    return {
        "summary": result.get("summary", ""),
        "architecture_score": result.get("architecture_score"),
        "integrity_score": result.get("integrity_score"),
        "analysis_id": result.get("analysis_id"),
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
    from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    prompt = args.get("prompt")
    if not prompt:
        raise ValueError("arm.generate requires 'prompt'")

    analyzer = DeepSeekCodeAnalyzer()
    result = analyzer.generate_code(
        prompt=prompt,
        user_id=user_id,
        db=db,
        language=args.get("language", "python"),
        original_code=args.get("original_code", ""),
    )
    return {
        "generated_code": result.get("generated_code", ""),
        "explanation": result.get("explanation", ""),
        "generation_id": result.get("generation_id"),
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
    from services.leadgen_service import run_ai_search

    query = args.get("query")
    if not query:
        raise ValueError("leadgen.search requires 'query'")

    leads = run_ai_search(query=query, user_id=user_id, db=db)
    return {"leads": leads, "count": len(leads)}


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
    from modules.research_engine import web_search

    query = args.get("query")
    if not query:
        raise ValueError("research.query requires 'query'")

    raw = web_search(query)
    return {"raw_result": raw[:2000] if raw else ""}


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
    from services.flow_engine import execute_intent

    message = args.get("message")
    session_id = args.get("session_id")
    if not message:
        raise ValueError("genesis.message requires 'message'")
    if not session_id:
        raise ValueError("genesis.message requires 'session_id'")

    result = execute_intent(
        intent_data={
            "workflow_type": "genesis_message",
            "session_id": session_id,
            "message": message,
        },
        db=db,
        user_id=user_id,
    )
    return result

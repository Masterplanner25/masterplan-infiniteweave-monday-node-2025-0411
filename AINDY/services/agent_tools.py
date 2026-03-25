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
    @register_tool("name", risk="low|medium|high", description="...")
    def my_tool(args: dict, user_id: str, db) -> dict: ...

The TOOL_REGISTRY dict maps tool_name → {fn, risk, description}.
"""
import logging
from typing import Callable

logger = logging.getLogger(__name__)

# ── Registry ─────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, dict] = {}


def register_tool(name: str, risk: str, description: str):
    """
    Decorator to register an agent tool.

    Usage:
        @register_tool("task.create", risk="low", description="Create a new task")
        def task_create(args: dict, user_id: str, db) -> dict:
            ...
    """
    def wrapper(fn: Callable) -> Callable:
        TOOL_REGISTRY[name] = {
            "fn": fn,
            "risk": risk,
            "description": description,
        }
        return fn
    return wrapper


def execute_tool(
    tool_name: str,
    args: dict,
    user_id: str,
    db,
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


def suggest_tools(kpi_snapshot: dict) -> list:
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
)
def task_complete(args: dict, user_id: str, db) -> dict:
    from services.task_services import complete_task

    name = args.get("name") or args.get("task_name")
    if not name:
        raise ValueError("task.complete requires 'name'")

    result = complete_task(db=db, name=name, user_id=user_id)
    return {"message": result}


@register_tool(
    "memory.recall",
    risk="low",
    description="Recall relevant memory nodes for a given query",
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
)
def genesis_message(args: dict, user_id: str, db) -> dict:
    from services.genesis_ai import call_genesis_llm

    message = args.get("message")
    if not message:
        raise ValueError("genesis.message requires 'message'")

    current_state = args.get("current_state") or {}
    result = call_genesis_llm(
        message=message,
        current_state=current_state,
        user_id=user_id,
        db=db,
    )
    return {
        "reply": result.get("reply", ""),
        "synthesis_ready": result.get("synthesis_ready", False),
        "state_update": result.get("state_update", {}),
    }

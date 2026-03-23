"""
Flow Definitions — A.I.N.D.Y. workflow graphs.

Defines the flow graph for each major workflow.
Registers nodes for each workflow.
Called at startup to populate NODE_REGISTRY and FLOW_REGISTRY.

Each node function wraps existing service logic —
no behavior changes, just wrapped in the node contract:
  fn(state, context) → result dict.
"""
import logging

from services.flow_engine import FLOW_REGISTRY, NODE_REGISTRY, register_flow, register_node

logger = logging.getLogger(__name__)


# ── ARM Analysis Flow ──────────────────────────────────────────────────────────


@register_node("arm_validate_input")
def arm_validate_input(state, context):
    """Validate ARM analysis input."""
    if not state.get("file_path"):
        return {"status": "FAILURE", "error": "file_path required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("arm_analyze_code")
def arm_analyze_code(state, context):
    """
    Run ARM analysis via existing service.
    Wraps DeepSeekCodeAnalyzer.run_analysis().
    """
    try:
        from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

        db = context.get("db")
        user_id = context.get("user_id")
        file_path = state.get("file_path")

        analyzer = DeepSeekCodeAnalyzer()
        result = analyzer.run_analysis(
            file_path=file_path,
            user_id=user_id,
            db=db,
        )

        return {
            "status": "SUCCESS",
            "output_patch": {
                "analysis_result": result,
                "analysis_score": result.get("architecture_score", 5),
            },
        }
    except Exception as e:
        logger.error("ARM analysis node failed: %s", e)
        return {"status": "RETRY", "error": str(e)}


@register_node("arm_store_result")
def arm_store_result(state, context):
    """Store ARM result via capture engine."""
    try:
        from services.memory_capture_engine import MemoryCaptureEngine

        db = context.get("db")
        user_id = context.get("user_id")
        result = state.get("analysis_result", {})

        if db and user_id:
            engine = MemoryCaptureEngine(db=db, user_id=user_id, agent_namespace="arm")
            engine.evaluate_and_capture(
                event_type="arm_analysis_complete",
                content=str(result)[:500],
                source="flow_engine:arm_analysis",
                context={"score": state.get("analysis_score", 5)},
            )

        return {"status": "SUCCESS", "output_patch": {"stored": True}}
    except Exception as e:
        logger.warning("ARM store node failed (non-fatal): %s", e)
        # Storage failure is non-fatal
        return {"status": "SUCCESS", "output_patch": {"stored": False}}


# ── Task Completion Flow ───────────────────────────────────────────────────────


@register_node("task_validate")
def task_validate(state, context):
    """Validate task completion input."""
    if not state.get("task_name"):
        return {"status": "FAILURE", "error": "task_name required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("task_complete")
def task_complete(state, context):
    """Complete task via existing service."""
    try:
        from services.task_services import complete_task

        db = context.get("db")
        user_id = context.get("user_id")
        task_name = state.get("task_name")

        result = complete_task(db=db, name=task_name, user_id=user_id)

        return {"status": "SUCCESS", "output_patch": {"task_result": result}}
    except Exception as e:
        return {"status": "RETRY", "error": str(e)}


@register_node("task_store_outcome")
def task_store_outcome(state, context):
    """Store task outcome via capture engine."""
    try:
        from services.memory_capture_engine import MemoryCaptureEngine

        db = context.get("db")
        user_id = context.get("user_id")
        task_result = state.get("task_result", {})

        if db and user_id:
            engine = MemoryCaptureEngine(db=db, user_id=user_id, agent_namespace="user")
            engine.evaluate_and_capture(
                event_type="task_completed",
                content=f"Task completed: {str(task_result)[:300]}",
                source="flow_engine:task_completion",
            )

        return {"status": "SUCCESS", "output_patch": {"stored": True}}
    except Exception as e:
        logger.warning("Task store node failed (non-fatal): %s", e)
        return {"status": "SUCCESS", "output_patch": {"stored": False}}


# ── LeadGen Search Flow ────────────────────────────────────────────────────────


@register_node("leadgen_validate")
def leadgen_validate(state, context):
    """Validate leadgen search input."""
    if not state.get("query"):
        return {"status": "FAILURE", "error": "query required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("leadgen_search")
def leadgen_search_node(state, context):
    """Run leadgen search via existing service."""
    try:
        from services.leadgen_service import run_ai_search

        db = context.get("db")
        user_id = context.get("user_id")

        results = run_ai_search(
            query=state.get("query"),
            user_id=user_id,
            db=db,
        )

        return {"status": "SUCCESS", "output_patch": {"search_results": results}}
    except Exception as e:
        return {"status": "RETRY", "error": str(e)}


@register_node("leadgen_store")
def leadgen_store(state, context):
    """Store leadgen results via capture engine."""
    try:
        from services.memory_capture_engine import MemoryCaptureEngine

        db = context.get("db")
        user_id = context.get("user_id")
        results = state.get("search_results", [])

        if db and user_id and results:
            engine = MemoryCaptureEngine(
                db=db, user_id=user_id, agent_namespace="leadgen"
            )
            engine.evaluate_and_capture(
                event_type="leadgen_search",
                content=f"LeadGen: {str(results)[:300]}",
                source="flow_engine:leadgen",
            )

        return {"status": "SUCCESS", "output_patch": {"stored": True}}
    except Exception as e:
        return {"status": "SUCCESS", "output_patch": {"stored": False}}


# ── Flow Registrations ─────────────────────────────────────────────────────────


def register_all_flows() -> None:
    """
    Register all A.I.N.D.Y. workflow flows.
    Called at startup from main.py lifespan.
    """
    register_flow(
        "arm_analysis",
        {
            "start": "arm_validate_input",
            "edges": {
                "arm_validate_input": ["arm_analyze_code"],
                "arm_analyze_code": ["arm_store_result"],
            },
            "end": ["arm_store_result"],
        },
    )

    register_flow(
        "task_completion",
        {
            "start": "task_validate",
            "edges": {
                "task_validate": ["task_complete"],
                "task_complete": ["task_store_outcome"],
            },
            "end": ["task_store_outcome"],
        },
    )

    register_flow(
        "leadgen_search",
        {
            "start": "leadgen_validate",
            "edges": {
                "leadgen_validate": ["leadgen_search"],
                "leadgen_search": ["leadgen_store"],
            },
            "end": ["leadgen_store"],
        },
    )

    logger.info(
        "Flow Engine: %d flows registered, %d nodes registered",
        len(FLOW_REGISTRY),
        len(NODE_REGISTRY),
    )

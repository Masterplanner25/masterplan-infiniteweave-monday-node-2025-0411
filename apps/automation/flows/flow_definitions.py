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

from AINDY.core.execution_signal_helper import queue_memory_capture
from AINDY.runtime.flow_engine import FLOW_REGISTRY, NODE_REGISTRY, register_flow, register_node
from apps.automation.flows.flow_definitions_extended import register_extended_flows  # noqa: F401

logger = logging.getLogger(__name__)


def _syscall_node(name: str, state: dict, context: dict, capability: str) -> dict:
    """Dispatch a syscall from a flow node and translate the response.

    Maps syscall envelope → flow node result contract:
      success → {"status": "SUCCESS", "output_patch": data}
      error   → {"status": "RETRY",   "error": message}

    This is the standard thin-wrapper pattern for all refactored flow nodes.
    """
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher, make_syscall_ctx_from_flow

    base_ctx = make_syscall_ctx_from_flow(context, capabilities=[capability])
    ctx = SyscallContext(
        execution_unit_id=base_ctx.execution_unit_id,
        user_id=base_ctx.user_id,
        capabilities=base_ctx.capabilities,
        trace_id=base_ctx.trace_id,
        memory_context=base_ctx.memory_context,
        metadata={
            **(base_ctx.metadata or {}),
            "_db": context.get("db"),
        },
    )
    result = get_dispatcher().dispatch(name, state, ctx)
    if result["status"] == "error":
        return {"status": "RETRY", "error": result["error"]}
    return {"status": "SUCCESS", "output_patch": result["data"]}


def _syscall_data(name: str, state: dict, context: dict, capability: str) -> dict:
    result = _syscall_node(name, state, context, capability)
    if result.get("status") != "SUCCESS":
        raise RuntimeError(result.get("error") or f"{name} failed")
    return result.get("output_patch") or {}


# ── ARM Analysis Flow ──────────────────────────────────────────────────────────


@register_node("arm_validate_input")
def arm_validate_input(state, context):
    """Validate ARM analysis input."""
    if not state.get("file_path"):
        return {"status": "FAILURE", "error": "file_path required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("arm_analyze_code")
def arm_analyze_code(state, context):
    """Run ARM analysis via sys.v1.arm.analyze syscall."""
    return _syscall_node("sys.v1.arm.analyze", state, context, "arm.analyze")


@register_node("arm_store_result")
def arm_store_result(state, context):
    """Store ARM result via sys.v1.arm.store syscall."""
    payload = {
        "result": state.get("analysis_result", {}),
        "event_type": "arm_analysis_complete",
        "score": state.get("analysis_score", 5),
    }
    return _syscall_node("sys.v1.arm.store", payload, context, "arm.store")


# ── Task Completion Flow ───────────────────────────────────────────────────────


@register_node("task_validate")
def task_validate(state, context):
    """Validate task completion input."""
    if not state.get("task_name"):
        return {"status": "FAILURE", "error": "task_name required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("task_complete")
def task_complete(state, context):
    """Complete task via sys.v1.task.complete syscall."""
    return _syscall_node("sys.v1.task.complete", state, context, "task.complete")


@register_node("task_orchestrate")
def task_orchestrate(state, context):
    """Post-completion task orchestration via sys.v1.task.orchestrate syscall."""
    result = _syscall_node("sys.v1.task.orchestrate", state, context, "task.orchestrate")
    # task_orchestrate maps RETRY → FAILURE (non-retryable orchestration)
    if result.get("status") == "RETRY":
        return {"status": "FAILURE", "error": result.get("error", "")}
    return result


# ── LeadGen Search Flow ────────────────────────────────────────────────────────


@register_node("leadgen_validate")
def leadgen_validate(state, context):
    """Validate leadgen search input."""
    if not state.get("query"):
        return {"status": "FAILURE", "error": "query required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("leadgen_search")
def leadgen_search_node(state, context):
    """Run leadgen search via sys.v1.leadgen.search syscall."""
    result = _syscall_node("sys.v1.leadgen.search", state, context, "leadgen.search")
    if result.get("status") == "RETRY" and "HTTP_503:" in (result.get("error") or ""):
        return {"status": "FAILURE", "error": result["error"]}
    # Rename data key to match expected state key
    if result.get("status") == "SUCCESS":
        data = result.get("output_patch", {})
        return {"status": "SUCCESS", "output_patch": {"search_results": data.get("search_results", [])}}
    return result


@register_node("leadgen_store")
def leadgen_store(state, context):
    """Store leadgen results via sys.v1.leadgen.store syscall."""
    payload = {
        "query": state.get("query", ""),
        "results": state.get("search_results", []),
    }
    return _syscall_node("sys.v1.leadgen.store", payload, context, "leadgen.store")




# ── Genesis Conversation Flow ──────────────────────────────────────────────────


@register_node("genesis_validate_session")
def genesis_validate_session(state, context):
    """Validate genesis session input before tracking."""
    if not state.get("session_id"):
        return {"status": "FAILURE", "error": "session_id required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("genesis_record_exchange")
def genesis_record_exchange(state, context):
    """
    Track a genesis message exchange.

    Does NOT call the LLM — the router handles that.
    Reads synthesis_ready from state or resumed event payload.
    Returns WAIT if conversation still active; SUCCESS if synthesis is ready.
    """
    synthesis_ready = state.get("synthesis_ready", False) or state.get(
        "event", {}
    ).get("synthesis_ready", False)

    if synthesis_ready:
        return {"status": "SUCCESS", "output_patch": {"synthesis_ready": True}}
    return {"status": "WAIT", "wait_for": "genesis_user_message"}


@register_node("genesis_store_synthesis")
def genesis_store_synthesis(state, context):
    """Store genesis synthesis completion to Memory Bridge."""
    try:
        db = context.get("db")
        user_id = context.get("user_id")
        session_id = state.get("session_id")

        if db and user_id:
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="genesis",
                event_type="genesis_synthesized",
                content=(
                    f"Genesis conversation {session_id} synthesis complete "
                    f"via Flow Engine."
                ),
                source="flow_engine:genesis_conversation",
                tags=["genesis", "synthesis", "flow_engine"],
                node_type="decision",
            )
        return {"status": "SUCCESS", "output_patch": {"stored": True}}
    except Exception as e:
        logger.warning("genesis_store_synthesis failed (non-fatal): %s", e)
        return {"status": "SUCCESS", "output_patch": {"stored": False}}


@register_node("genesis_message_validate")
def genesis_message_validate(state, context):
    if not state.get("session_id"):
        return {"status": "FAILURE", "error": "session_id required"}
    if not state.get("message"):
        return {"status": "FAILURE", "error": "message required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("genesis_message_execute")
def genesis_message_execute(state, context):
    """Call Genesis LLM and update session via sys.v1.genesis.execute_llm syscall."""
    result = _syscall_node("sys.v1.genesis.execute_llm", state, context, "genesis.execute_llm")
    if result.get("status") == "RETRY" and "HTTP_503:" in (result.get("error") or ""):
        return {"status": "FAILURE", "error": result["error"]}
    # Handler failure for "not found" should be FAILURE not RETRY
    if result.get("status") == "RETRY" and "not found" in (result.get("error") or "").lower():
        return {"status": "FAILURE", "error": result["error"]}
    return result


@register_node("genesis_message_orchestrate")
def genesis_message_orchestrate(state, context):
    try:
        orchestration = _syscall_data(
            "sys.v1.analytics.execute_infinity",
            {"user_id": context.get("user_id"), "trigger_event": "genesis_message"},
            context,
            "score.recalculate",
        )
        response = dict(state.get("genesis_response") or {})
        response["orchestration"] = orchestration
        return {"status": "SUCCESS", "output_patch": {"genesis_response": response}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_execution_validate")
def memory_execution_validate(state, context):
    if not state.get("original_workflow"):
        return {"status": "FAILURE", "error": "workflow is required"}
    if not isinstance(state.get("execution_input"), dict):
        return {"status": "FAILURE", "error": "execution_input must be an object"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("memory_execution_run")
def memory_execution_run(state, context):
    try:
        from types import SimpleNamespace

        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.execution_registry import REGISTRY
        from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts
        from AINDY.runtime.memory_loop import ExecutionLoop

        db = context.get("db")
        user_id = context.get("user_id")
        workflow = state.get("original_workflow")
        session_tags = state.get("session_tags") or []
        execution_input = state.get("execution_input") or {}

        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        loop = ExecutionLoop(orchestrator)

        def leadgen_handler(payload, owner_user_id, owner_db):
            query = payload.get("query") or payload.get("input") or payload.get("message")
            if not query:
                return {"error": "missing_query", "message": "missing query"}
            return _syscall_data(
                "sys.v1.leadgen.search",
                {"query": str(query)},
                {**context, "db": owner_db, "user_id": owner_user_id},
                "leadgen.search",
            )

        def genesis_handler(payload, owner_user_id, owner_db):
            message = payload.get("message") or payload.get("query") or payload.get("input")
            if not message:
                return {"error": "missing_message", "message": "missing message"}
            return _syscall_data(
                "sys.v1.genesis.call_llm",
                {
                    "message": str(message),
                    "current_state": payload.get("current_state") or payload.get("state") or {},
                },
                {**context, "db": owner_db, "user_id": owner_user_id},
                "genesis.execute_llm",
            )

        REGISTRY.register("leadgen", leadgen_handler)
        REGISTRY.register("genesis_message", genesis_handler)

        def executor(task, _memory_context):
            return REGISTRY.execute(
                workflow=task.type,
                payload=task.input,
                user_id=user_id,
                db=db,
            )

        loop.executor = executor
        task = SimpleNamespace(
            type=workflow,
            input=execution_input,
            source=f"memory_loop:{workflow}",
            tags=session_tags,
            metadata={
                "trace_enabled": True,
                "trace_title": workflow,
                "trace_description": None,
                "trace_extra": execution_input,
            },
        )
        result, memory_context = loop.run_with_context(task, user_id, db)
        recalled_memories = memory_items_to_dicts(memory_context.items) if memory_context else []
        return {
            "status": "SUCCESS",
            "output_patch": {
                "memory_execution_response": {
                    "workflow": workflow,
                    "user_id": str(user_id),
                    "session_tags": session_tags,
                    "result": result,
                    "recalled_memories": recalled_memories,
                    "recall_count": len(recalled_memories),
                    "memory_bridge_version": "v5",
                    "trace_id": task.metadata.get("trace_id"),
                    "memory_context": memory_context.formatted if memory_context else "",
                }
            },
        }
    except Exception as e:
        return {"status": "RETRY", "error": str(e)}


@register_node("memory_execution_orchestrate")
def memory_execution_orchestrate(state, context):
    response = dict(state.get("memory_execution_response") or {})
    try:
        workflow = state.get("original_workflow")
        orchestration = _syscall_data(
            "sys.v1.analytics.execute_infinity",
            {"user_id": context.get("user_id"), "trigger_event": f"memory_{workflow}"},
            context,
            "score.recalculate",
        )
        response["orchestration"] = orchestration
        return {"status": "SUCCESS", "output_patch": {"memory_execution_response": response}}
    except Exception as e:
        response["orchestration"] = None
        response["orchestration_error"] = str(e)
        return {"status": "SUCCESS", "output_patch": {"memory_execution_response": response}}


# ── Task Create Flow ──────────────────────────────────────────────────────────


@register_node("task_create_validate")
def task_create_validate(state, context):
    """Validate task creation input."""
    if not state.get("task_name"):
        return {"status": "FAILURE", "error": "task_name required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("task_create_execute")
def task_create_execute(state, context):
    """Create a task via sys.v1.task.create syscall."""
    return _syscall_node("sys.v1.task.create", state, context, "task.create")


# ── Task Start Flow ────────────────────────────────────────────────────────────


@register_node("task_start_execute")
def task_start_execute(state, context):
    """Start a task via sys.v1.task.start syscall."""
    return _syscall_node("sys.v1.task.start", state, context, "task.start")


# ── Task Pause Flow ────────────────────────────────────────────────────────────


@register_node("task_pause_execute")
def task_pause_execute(state, context):
    """Pause a task via sys.v1.task.pause syscall."""
    return _syscall_node("sys.v1.task.pause", state, context, "task.pause")


# ── Goal Create Flow ───────────────────────────────────────────────────────────


@register_node("goal_create_validate")
def goal_create_validate(state, context):
    """Validate goal creation input."""
    if not state.get("name"):
        return {"status": "FAILURE", "error": "name required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("goal_create_execute")
def goal_create_execute(state, context):
    """Create a goal via sys.v1.goal.create syscall."""
    return _syscall_node("sys.v1.goal.create", state, context, "goal.create")


# ── Score Recalculate Flow ─────────────────────────────────────────────────────


@register_node("score_recalculate_execute")
def score_recalculate_execute(state, context):
    """Recalculate the user's Infinity Score via sys.v1.score.recalculate syscall."""
    return _syscall_node("sys.v1.score.recalculate", state, context, "score.recalculate")


# ── Score Feedback Flow ────────────────────────────────────────────────────────


@register_node("score_feedback_execute")
def score_feedback_execute(state, context):
    """Persist a score feedback record via sys.v1.score.feedback syscall."""
    return _syscall_node("sys.v1.score.feedback", state, context, "score.feedback")


# ── ARM Generate Flow ──────────────────────────────────────────────────────────


@register_node("arm_generate_validate")
def arm_generate_validate(state, context):
    """Validate ARM code generation input."""
    if not state.get("prompt"):
        return {"status": "FAILURE", "error": "prompt required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("arm_generate_code")
def arm_generate_code(state, context):
    """Run ARM code generation via sys.v1.arm.generate syscall."""
    return _syscall_node("sys.v1.arm.generate", state, context, "arm.generate")


@register_node("arm_generate_store")
def arm_generate_store(state, context):
    """Store ARM generation result to Memory Bridge via sys.v1.arm.store syscall."""
    payload = {
        "result": state.get("generation_result", {}),
        "event_type": "arm_generate_complete",
    }
    return _syscall_node("sys.v1.arm.store", payload, context, "arm.store")


# ── Watcher Ingest Flow ────────────────────────────────────────────────────────


@register_node("watcher_ingest_validate")
def watcher_ingest_validate(state, context):
    signals = state.get("signals") or []
    if not isinstance(signals, list) or not signals:
        return {"status": "FAILURE", "error": "signals are required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("watcher_ingest_persist")
def watcher_ingest_persist(state, context):
    """Persist watcher signals via sys.v1.watcher.ingest syscall."""
    return _syscall_node("sys.v1.watcher.ingest", state, context, "watcher.ingest")


@register_node("watcher_ingest_orchestrate")
def watcher_ingest_orchestrate(state, context):
    try:
        from uuid import UUID

        from AINDY.core.system_event_service import emit_system_event

        db = context.get("db")
        session_ended_count = state.get("watcher_session_ended_count") or 0
        batch_user_id = state.get("watcher_batch_user_id")

        eta_recalculated = False
        score_orchestrated = False
        next_action = None

        if session_ended_count > 0:
            event_user_id = UUID(str(batch_user_id)) if batch_user_id else None
            signals = state.get("signals") or []
            ended_signals = [
                signal
                for signal in signals
                if isinstance(signal, dict)
                and signal.get("signal_type") == "session_ended"
            ]
            event_payload = {
                "session_ended_count": session_ended_count,
                "signals": ended_signals,
            }
            if len(ended_signals) == 1:
                signal = ended_signals[0]
                metadata = signal.get("metadata") or {}
                event_payload.update(
                    {
                        "session_duration": metadata.get("session_duration")
                        or metadata.get("duration_seconds"),
                        "focus_score": metadata.get("focus_score"),
                        "session_id": signal.get("session_id"),
                        "activity_type": signal.get("activity_type"),
                    }
                )
            emit_system_event(
                db=db,
                event_type="watcher.session_ended",
                user_id=event_user_id,
                source="watcher_ingest",
                payload=event_payload,
                required=True,
                skip_memory_capture=True,
            )
            eta_recalculated = True
            if batch_user_id:
                orchestration = _syscall_data(
                    "sys.v1.analytics.execute_infinity",
                    {"user_id": str(event_user_id), "trigger_event": "session_ended"},
                    context,
                    "score.recalculate",
                )
                score_orchestrated = True
                next_action = orchestration["next_action"]

        result = dict(state.get("watcher_ingest_result") or {})
        result["orchestration"] = {
            "eta_recalculated": eta_recalculated,
            "score_orchestrated": score_orchestrated,
            "next_action": next_action,
        }
        return {"status": "SUCCESS", "output_patch": {"watcher_ingest_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


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
        "arm_generate",
        {
            "start": "arm_generate_validate",
            "edges": {
                "arm_generate_validate": ["arm_generate_code"],
                "arm_generate_code": ["arm_generate_store"],
            },
            "end": ["arm_generate_store"],
        },
    )

    register_flow(
        "task_create",
        {
            "start": "task_create_validate",
            "edges": {
                "task_create_validate": ["task_create_execute"],
            },
            "end": ["task_create_execute"],
        },
    )

    register_flow(
        "task_start",
        {
            "start": "task_start_execute",
            "edges": {},
            "end": ["task_start_execute"],
        },
    )

    register_flow(
        "task_pause",
        {
            "start": "task_pause_execute",
            "edges": {},
            "end": ["task_pause_execute"],
        },
    )

    register_flow(
        "goal_create",
        {
            "start": "goal_create_validate",
            "edges": {
                "goal_create_validate": ["goal_create_execute"],
            },
            "end": ["goal_create_execute"],
        },
    )

    register_flow(
        "score_recalculate",
        {
            "start": "score_recalculate_execute",
            "edges": {},
            "end": ["score_recalculate_execute"],
        },
    )

    register_flow(
        "score_feedback",
        {
            "start": "score_feedback_execute",
            "edges": {},
            "end": ["score_feedback_execute"],
        },
    )

    register_flow(
        "task_completion",
        {
            "start": "task_validate",
            "edges": {
                "task_validate": ["task_complete"],
                "task_complete": ["task_orchestrate"],
            },
            "end": ["task_orchestrate"],
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

    register_flow(
        "genesis_conversation",
        {
            "start": "genesis_validate_session",
            "edges": {
                "genesis_validate_session": ["genesis_record_exchange"],
                # Conditional: advance to synthesis store when ready;
                # WAIT without a matching edge is handled by the WAIT/RESUME
                # contract — current_node stays at genesis_record_exchange
                # until synthesis_ready becomes True.
                "genesis_record_exchange": [
                    {
                        "condition": lambda s: (
                            s.get("synthesis_ready", False)
                            or s.get("event", {}).get("synthesis_ready", False)
                        ),
                        "target": "genesis_store_synthesis",
                    }
                ],
            },
            "end": ["genesis_store_synthesis"],
            "wait_timeout_minutes": 120,
        },
    )

    register_flow(
        "genesis_message",
        {
            "start": "genesis_message_validate",
            "edges": {
                "genesis_message_validate": ["genesis_message_execute"],
                "genesis_message_execute": ["genesis_message_orchestrate"],
            },
            "end": ["genesis_message_orchestrate"],
        },
    )

    register_flow(
        "memory_execution",
        {
            "start": "memory_execution_validate",
            "edges": {
                "memory_execution_validate": ["memory_execution_run"],
                "memory_execution_run": ["memory_execution_orchestrate"],
            },
            "end": ["memory_execution_orchestrate"],
        },
    )

    register_flow(
        "watcher_ingest",
        {
            "start": "watcher_ingest_validate",
            "edges": {
                "watcher_ingest_validate": ["watcher_ingest_persist"],
                "watcher_ingest_persist": ["watcher_ingest_orchestrate"],
            },
            "end": ["watcher_ingest_orchestrate"],
        },
    )

    register_extended_flows()

    logger.info(
        "Flow Engine: %d flows registered, %d nodes registered",
        len(FLOW_REGISTRY),
        len(NODE_REGISTRY),
    )


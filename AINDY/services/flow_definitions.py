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

from core.execution_signal_helper import queue_memory_capture
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
        db = context.get("db")
        user_id = context.get("user_id")
        result = state.get("analysis_result", {})

        if db and user_id:
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="arm",
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
    """Complete task via the core task mutation service."""
    try:
        from services.task_services import complete_task

        db = context.get("db")
        user_id = context.get("user_id")
        task_name = state.get("task_name")

        result = complete_task(db=db, name=task_name, user_id=user_id)

        return {"status": "SUCCESS", "output_patch": {"task_result": result}}
    except Exception as e:
        return {"status": "RETRY", "error": str(e)}


@register_node("task_orchestrate")
def task_orchestrate(state, context):
    """Run the structured post-completion orchestration for a task."""
    try:
        from services.task_services import orchestrate_task_completion
        db = context.get("db")
        user_id = context.get("user_id")
        task_name = state.get("task_name")
        orchestration = orchestrate_task_completion(
            db=db,
            name=task_name,
            user_id=user_id,
        )
        return {
            "status": "SUCCESS",
            "output_patch": {"task_orchestration": orchestration},
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


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
        db = context.get("db")
        user_id = context.get("user_id")
        results = state.get("search_results", [])

        if db and user_id and results:
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="leadgen",
                event_type="leadgen_search",
                content=f"LeadGen: {str(results)[:300]}",
                source="flow_engine:leadgen",
            )

        return {"status": "SUCCESS", "output_patch": {"stored": True}}
    except Exception as e:
        return {"status": "SUCCESS", "output_patch": {"stored": False}}


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
    try:
        import uuid

        from db.models import GenesisSessionDB
        from services.genesis_ai import call_genesis_llm

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session = (
            db.query(GenesisSessionDB)
            .filter(
                GenesisSessionDB.id == state.get("session_id"),
                GenesisSessionDB.user_id == user_id,
            )
            .first()
        )
        if not session:
            return {"status": "FAILURE", "error": "GenesisSession not found"}

        current_state = session.summarized_state or {}
        llm_output = call_genesis_llm(
            message=state.get("message"),
            current_state=current_state,
            user_id=str(user_id),
            db=db,
        )

        state_update = llm_output.get("state_update", {})
        for key, value in state_update.items():
            if key in current_state and value is not None:
                current_state[key] = value

        if "confidence" in current_state:
            current_state["confidence"] = max(0.0, min(current_state["confidence"], 1.0))

        session.summarized_state = current_state
        if llm_output.get("synthesis_ready", False) and not session.synthesis_ready:
            session.synthesis_ready = True
        db.commit()

        return {
            "status": "SUCCESS",
            "output_patch": {
                "genesis_response": {
                    "reply": llm_output.get("reply", ""),
                    "synthesis_ready": session.synthesis_ready,
                }
            },
        }
    except Exception as e:
        return {"status": "RETRY", "error": str(e)}


@register_node("genesis_message_orchestrate")
def genesis_message_orchestrate(state, context):
    try:
        from services.infinity_orchestrator import execute as execute_infinity_orchestrator

        db = context.get("db")
        user_id = context.get("user_id")
        orchestration = execute_infinity_orchestrator(
            user_id=user_id,
            trigger_event="genesis_message",
            db=db,
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

        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.execution_loop import ExecutionLoop
        from runtime.execution_registry import REGISTRY
        from runtime.memory import MemoryOrchestrator, memory_items_to_dicts
        from services.genesis_ai import call_genesis_llm
        from services.leadgen_service import create_lead_results

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
            return create_lead_results(db=owner_db, query=str(query), user_id=owner_user_id)

        def genesis_handler(payload, owner_user_id, owner_db):
            message = payload.get("message") or payload.get("query") or payload.get("input")
            current_state = payload.get("current_state") or payload.get("state") or {}
            if not message:
                return {"error": "missing_message", "message": "missing message"}
            return call_genesis_llm(message=str(message), current_state=current_state, user_id=owner_user_id, db=owner_db)

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
            source=f"execution_loop:{workflow}",
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
    try:
        from services.infinity_orchestrator import execute as execute_infinity_orchestrator

        db = context.get("db")
        user_id = context.get("user_id")
        workflow = state.get("original_workflow")
        orchestration = execute_infinity_orchestrator(
            user_id=user_id,
            trigger_event=f"memory_{workflow}",
            db=db,
        )
        response = dict(state.get("memory_execution_response") or {})
        response["orchestration"] = orchestration
        return {"status": "SUCCESS", "output_patch": {"memory_execution_response": response}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("watcher_ingest_validate")
def watcher_ingest_validate(state, context):
    signals = state.get("signals") or []
    if not isinstance(signals, list) or not signals:
        return {"status": "FAILURE", "error": "signals are required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


@register_node("watcher_ingest_persist")
def watcher_ingest_persist(state, context):
    try:
        from datetime import datetime, timezone
        from uuid import UUID

        from db.models.watcher_signal import WatcherSignal
        from routes.watcher_router import _VALID_ACTIVITY_TYPES, _VALID_SIGNAL_TYPES, _parse_timestamp

        db = context.get("db")
        signals = state.get("signals") or []
        persisted = 0
        session_ended_count = 0
        batch_user_id = None

        for idx, sig in enumerate(signals):
            signal_type = sig.get("signal_type")
            activity_type = sig.get("activity_type")
            if signal_type not in _VALID_SIGNAL_TYPES:
                return {"status": "FAILURE", "error": f"Signal [{idx}]: unknown signal_type {signal_type!r}"}
            if activity_type not in _VALID_ACTIVITY_TYPES:
                return {"status": "FAILURE", "error": f"Signal [{idx}]: unknown activity_type {activity_type!r}"}

            ts = _parse_timestamp(sig.get("timestamp"))
            meta = sig.get("metadata") or {}
            signal_user_id = sig.get("user_id")
            if signal_user_id and not batch_user_id:
                batch_user_id = signal_user_id

            row = WatcherSignal(
                signal_type=signal_type,
                session_id=sig.get("session_id"),
                user_id=UUID(str(signal_user_id)) if signal_user_id else None,
                app_name=sig.get("app_name"),
                window_title=sig.get("window_title") or None,
                activity_type=activity_type,
                signal_timestamp=ts,
                received_at=datetime.now(timezone.utc),
                duration_seconds=meta.get("duration_seconds"),
                focus_score=meta.get("focus_score"),
                signal_metadata=meta if meta else None,
            )
            db.add(row)
            if signal_type == "session_ended":
                session_ended_count += 1
            persisted += 1

        db.commit()
        return {
            "status": "SUCCESS",
            "output_patch": {
                "watcher_ingest_result": {
                    "accepted": persisted,
                    "session_ended_count": session_ended_count,
                },
                "watcher_batch_user_id": batch_user_id,
                "watcher_session_ended_count": session_ended_count,
            },
        }
    except Exception as e:
        return {"status": "RETRY", "error": str(e)}


@register_node("watcher_ingest_orchestrate")
def watcher_ingest_orchestrate(state, context):
    try:
        from uuid import UUID

        from services.eta_service import recalculate_all_etas
        from services.infinity_orchestrator import execute as execute_infinity_orchestrator

        db = context.get("db")
        session_ended_count = state.get("watcher_session_ended_count") or 0
        batch_user_id = state.get("watcher_batch_user_id")

        eta_recalculated = False
        score_orchestrated = False
        next_action = None

        if session_ended_count > 0:
            recalculate_all_etas(db=db)
            eta_recalculated = True
            if batch_user_id:
                orchestration = execute_infinity_orchestrator(
                    user_id=UUID(str(batch_user_id)),
                    db=db,
                    trigger_event="session_ended",
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

    logger.info(
        "Flow Engine: %d flows registered, %d nodes registered",
        len(FLOW_REGISTRY),
        len(NODE_REGISTRY),
    )

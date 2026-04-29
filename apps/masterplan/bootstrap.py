"""Masterplan domain bootstrap."""
from __future__ import annotations

import logging
import uuid
from uuid import UUID

logger = logging.getLogger(__name__)

BOOTSTRAP_DEPENDS_ON: list[str] = ["automation", "identity", "tasks"]
APP_DEPENDS_ON: list[str] = ["automation", "identity", "tasks"]


def register() -> None:
    _register_models()
    _register_routers()
    _register_route_prefixes()
    _register_response_adapters()
    _register_events()
    _register_jobs()
    _register_scheduled_jobs()
    _register_async_jobs()
    _register_agent_tools()
    _register_agent_capabilities()
    _register_agent_ranking()
    _register_capture_rules()
    _register_flow_results()
    _register_flow_plans()
    _register_syscalls()
    _register_required_syscalls()
    _register_health_check()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.masterplan.models as masterplan_models

    register_models(masterplan_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(masterplan_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.masterplan.routes.genesis_router import router as genesis_router
    from apps.masterplan.routes.goals_router import router as goals_router
    from apps.masterplan.routes.masterplan_router import router as masterplan_router
    from apps.masterplan.routes.score_router import router as score_router

    register_router(genesis_router)
    register_router(goals_router)
    register_router(masterplan_router)
    register_router(score_router)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix

    register_route_prefix("genesis", "flow")
    register_route_prefix("masterplan", "flow")


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter

    register_response_adapter("masterplan", raw_json_adapter)
    register_response_adapter("score", raw_json_adapter)
    register_response_adapter("scores", raw_json_adapter)


def _register_events() -> None:
    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import register_event_handler, register_event_type
    from apps.masterplan.events import MasterplanEventTypes
    from apps.masterplan.services.watcher_events import register_masterplan_event_handlers

    register_masterplan_event_handlers()
    for value in vars(MasterplanEventTypes).values():
        if isinstance(value, str):
            register_event_type(value)
    register_event_type(SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED)
    register_event_type(SystemEventTypes.EXECUTION_COMPLETED)
    register_event_type(SystemEventTypes.ANALYTICS_SCORE_UPDATED)
    register_event_handler(SystemEventTypes.EXECUTION_COMPLETED, _handle_execution_completed)
    register_event_handler(SystemEventTypes.ANALYTICS_SCORE_UPDATED, _handle_analytics_score_updated)


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job

    register_job("genesis.synthesize", _genesis_synthesize)
    register_job("genesis.audit", _genesis_audit)
    register_job("goals.rank", _rank_goals)
    register_job("goals.calculate_alignment", _calculate_goal_alignment)
    register_job("goals.update_from_execution", _update_goals_from_execution)
    register_job("scheduler.masterplan_eta", _scheduler_recalculate_all_etas)


def _register_scheduled_jobs() -> None:
    from AINDY.platform_layer.registry import register_scheduled_job

    register_scheduled_job(
        "daily_eta_recalculation",
        _scheduler_recalculate_all_etas,
        name="Daily ETA projection recalculation",
        trigger="cron",
        trigger_kwargs={"hour": 6},
    )


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job

    register_async_job("genesis.message")(_job_genesis_message)
    register_async_job("genesis.synthesize")(_job_genesis_synthesize)
    register_async_job("genesis.audit")(_job_genesis_audit)


def _register_agent_tools() -> None:
    from apps.masterplan.agents.tools import register as register_masterplan_tools
    register_masterplan_tools()


def _register_agent_capabilities() -> None:
    from apps.masterplan.agents.capabilities import register as register_masterplan_capabilities
    register_masterplan_capabilities()


def _register_agent_ranking() -> None:
    from apps.masterplan.agents.ranking import register
    register()


def _register_capture_rules() -> None:
    from AINDY.platform_layer.registry import register_memory_policy
    from apps.masterplan.memory_policy import register as register_masterplan_memory_policy
    register_masterplan_memory_policy(register_memory_policy)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "genesis_message": "genesis_response",
        "genesis_session_create": "genesis_session_create_result",
        "genesis_session_get": "genesis_session_get_result",
        "genesis_draft_get": "genesis_draft_get_result",
        "genesis_synthesize": "genesis_synthesize_result",
        "genesis_audit": "genesis_audit_result",
        "genesis_lock": "genesis_lock_result",
        "genesis_activate": "genesis_activate_result",
        "masterplan_lock_from_genesis": "masterplan_lock_from_genesis_result",
        "masterplan_lock": "masterplan_lock_result",
        "masterplan_list": "masterplan_list_result",
        "masterplan_get": "masterplan_get_result",
        "masterplan_anchor": "masterplan_anchor_result",
        "masterplan_projection": "masterplan_projection_result",
        "masterplan_activate": "masterplan_activate_result",
        "goal_create": "goal_create_result",
        "goals_list": "goals_list_result",
        "goals_state": "goals_state_result",
        "score_recalculate": "score_recalculate_result",
        "score_feedback": "score_feedback_result",
        "score_get": "score_get_result",
        "score_history": "score_history_result",
        "score_feedback_list": "score_feedback_list_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

    register_flow_result("genesis_conversation", completion_event="genesis_synthesized")


def _register_flow_plans() -> None:
    from AINDY.platform_layer.registry import register_flow_plan

    register_flow_plan(
        "genesis_conversation",
        {"steps": ["process_message", "store_insight"]},
    )
    register_flow_plan(
        "genesis_message",
        {"steps": ["genesis_message_validate", "genesis_message_execute", "genesis_message_orchestrate"]},
    )
    register_flow_plan(
        "genesis_lock",
        {"steps": ["validate_draft", "lock_masterplan", "store_decision"]},
    )


def _register_syscalls() -> None:
    from apps.masterplan.syscalls.syscall_handlers import register_masterplan_syscall_handlers
    from apps.masterplan.syscalls.dependency_cascade_syscall import (
        register_dependency_cascade_syscalls,
    )

    register_masterplan_syscall_handlers()
    register_dependency_cascade_syscalls()


def _register_required_syscalls() -> None:
    from AINDY.platform_layer.registry import register_required_syscall

    register_required_syscall("sys.v1.masterplan.cascade_activate")


def _job_genesis_message(payload: dict, db):
    from AINDY.runtime.flow_engine import execute_intent
    return execute_intent(
        intent_data={
            "workflow_type": "genesis_message",
            "session_id": payload["session_id"],
            "message": payload["message"],
        },
        db=db,
        user_id=payload["user_id"],
    )


def _job_genesis_synthesize(payload: dict, db):
    from apps.masterplan.models import GenesisSessionDB

    user_id = UUID(str(payload["user_id"]))
    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == payload["session_id"], GenesisSessionDB.user_id == user_id)
        .first()
    )
    if not session:
        raise RuntimeError("GenesisSession not found")
    if not session.synthesis_ready:
        raise RuntimeError("Session is not ready for synthesis")
    draft = _genesis_synthesize(session.summarized_state or {}, user_id=str(user_id), db=db)
    session.draft_json = draft
    db.commit()
    return {"draft": draft}


def _job_genesis_audit(payload: dict, db):
    from apps.masterplan.models import GenesisSessionDB

    user_id = UUID(str(payload["user_id"]))
    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == payload["session_id"], GenesisSessionDB.user_id == user_id)
        .first()
    )
    if not session or not session.draft_json:
        raise RuntimeError("No draft available")
    return _genesis_audit(session.draft_json, user_id=str(user_id), db=db)


def _genesis_synthesize(*args, **kwargs):
    from apps.masterplan.services.genesis_ai import call_genesis_synthesis_llm
    return call_genesis_synthesis_llm(*args, **kwargs)


def _genesis_audit(*args, **kwargs):
    from apps.masterplan.services.genesis_ai import validate_draft_integrity
    return validate_draft_integrity(*args, **kwargs)


def _rank_goals(*args, **kwargs):
    from apps.masterplan.services.goal_service import rank_goals
    return rank_goals(*args, **kwargs)


def _calculate_goal_alignment(*args, **kwargs):
    from apps.masterplan.services.goal_service import calculate_goal_alignment
    return calculate_goal_alignment(*args, **kwargs)


def _update_goals_from_execution(*args, **kwargs):
    from apps.masterplan.services.goal_service import update_goals_from_execution
    return update_goals_from_execution(*args, **kwargs)


def _handle_execution_completed(context: dict):
    from apps.masterplan.services.goal_service import update_goals_from_execution

    db = context.get("db")
    if db is None or "execution_result" not in context:
        return None
    return update_goals_from_execution(
        db,
        user_id=context.get("user_id"),
        workflow_type=context.get("workflow_type"),
        execution_result=context.get("execution_result"),
        success=context.get("success", True),
    )


def _handle_analytics_score_updated(context: dict):
    from apps.masterplan.services.goal_service import handle_score_updated

    return handle_score_updated(context)


def _scheduler_recalculate_all_etas() -> None:
    from AINDY.agents.autonomous_controller import evaluate_live_trigger, record_decision
    from AINDY.db.database import SessionLocal
    from apps.masterplan.services.eta_service import recalculate_all_etas

    try:
        db = SessionLocal()
    except Exception as exc:
        logger.warning("[ETA Scheduler] DB unavailable: %s", exc)
        return
    try:
        trigger = {"trigger_type": "schedule", "source": "scheduler.masterplan_eta", "goal": "daily_eta_recalculation"}
        context = {"goal": "daily_eta_recalculation", "importance": 0.55, "goal_alignment": 0.65}
        decision = evaluate_live_trigger(db=db, trigger=trigger, context=context)
        record_decision(db=db, trigger=trigger, evaluation=decision, trace_id=str(uuid.uuid4()), context=context)
        if decision["decision"] != "execute":
            logger.info("[ETA Scheduler] Deferred by autonomy controller: %s", decision["reason"])
            return
        updated = recalculate_all_etas(db)
        logger.info("[ETA Scheduler] Recalculated ETAs for %d plans", updated)
    finally:
        db.close()


def masterplan_health_check() -> bool:
    from AINDY.db.database import SessionLocal

    try:
        from AINDY.kernel.circuit_breaker import CircuitState
        from AINDY.platform_layer.openai_client import get_openai_circuit_breaker
    except Exception as exc:
        raise RuntimeError(f"masterplan health import failed: {exc}") from exc

    cb = get_openai_circuit_breaker()
    if cb.state == CircuitState.OPEN:
        raise RuntimeError(
            f"OpenAI circuit breaker is open - Genesis AI unavailable. Opened at: {cb.opened_at}"
        )

    try:
        from apps.masterplan.models import MasterPlan
    except Exception as exc:
        raise RuntimeError(f"masterplan model import failed: {exc}") from exc

    db = SessionLocal()
    try:
        db.query(MasterPlan.id).limit(1).all()
        return True
    finally:
        db.close()


def _register_health_check() -> None:
    from AINDY.platform_layer.domain_health import domain_health_registry
    from AINDY.platform_layer.registry import register_health_check

    domain_health_registry.register("masterplan", masterplan_health_check)
    register_health_check("masterplan", _check_health)


def _check_health() -> dict:
    db = None
    try:
        from AINDY.db.database import SessionLocal
        from apps.masterplan.goals import Goal

        db = SessionLocal()
        db.query(Goal.id).limit(1).all()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}
    finally:
        if db is not None:
            db.close()

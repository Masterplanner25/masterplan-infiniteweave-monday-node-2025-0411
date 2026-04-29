"""Analytics domain bootstrap."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)

BOOTSTRAP_DEPENDS_ON: list[str] = ["identity", "tasks"]
APP_DEPENDS_ON: list[str] = ["arm", "identity"]


def register() -> None:
    _register_models()
    _register_routers()
    _register_response_adapters()
    _register_events()
    _register_jobs()
    _register_scheduled_jobs()
    _register_syscalls()
    _register_required_syscalls()
    _register_flow_results()
    _register_health_check()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.analytics.models as analytics_models

    register_models(analytics_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(analytics_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.analytics.routes.analytics_router import router as analytics_router
    from apps.analytics.routes.main_router import router as main_router
    from apps.analytics.routes.main_router import legacy_router as legacy_main_router

    register_router(analytics_router)
    register_router(main_router)
    register_router(legacy_main_router, legacy_root=True)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter

    register_response_adapter("analytics", raw_json_adapter)
    register_response_adapter("main", raw_json_adapter)


def _register_events() -> None:
    from AINDY.platform_layer.registry import register_event_handler, register_event_type
    from AINDY.core.system_event_types import SystemEventTypes

    register_event_type(SystemEventTypes.ANALYTICS_SCORE_UPDATED)
    register_event_type(SystemEventTypes.EXECUTION_COMPLETED)
    register_event_type(SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED)
    register_event_handler(SystemEventTypes.EXECUTION_COMPLETED, _handle_execution_completed)
    register_event_handler(SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED, _handle_goal_state_changed)


def _handle_execution_completed(context: dict):
    db = context.get("db")
    if db is not None and context.get("trigger_event") == "agent_completed" and context.get("user_id"):
        from apps.analytics.services.orchestration.infinity_orchestrator import execute
        return execute(
            user_id=context["user_id"],
            trigger_event=context["trigger_event"],
            db=db,
        )
    return None


def _handle_goal_state_changed(context: dict):
    from apps.analytics.services.orchestration.infinity_orchestrator import handle_goal_state_changed

    return handle_goal_state_changed(context)


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job

    register_job("analytics.kpi_snapshot", _get_user_kpi_snapshot)
    register_job("analytics.infinity_execute", _execute_infinity_orchestrator)
    register_job("analytics.latest_adjustment", _get_latest_adjustment)
    register_job("analytics.latest_adjustment_payload", _get_latest_adjustment_payload)
    register_job("scheduler.infinity_scores", _scheduler_recalculate_all_scores)


def _register_scheduled_jobs() -> None:
    from AINDY.platform_layer.registry import register_scheduled_job

    register_scheduled_job(
        "daily_infinity_score_recalculation",
        _scheduler_recalculate_all_scores,
        name="Daily Infinity score recalculation",
        trigger="cron",
        trigger_kwargs={"hour": 7},
    )


def _register_syscalls() -> None:
    from apps.analytics.syscalls import register_analytics_syscall_handlers

    register_analytics_syscall_handlers()


def _register_required_syscalls() -> None:
    from AINDY.platform_layer.registry import register_required_syscall

    for name in (
        "sys.v1.analytics.get_kpi_snapshot",
        "sys.v1.analytics.execute_infinity",
        "sys.v1.analytics.get_latest_adjustment",
        "sys.v1.score.recalculate",
    ):
        register_required_syscall(name)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "analytics_linkedin_ingest": "analytics_linkedin_ingest_result",
        "analytics_masterplan_get": "analytics_masterplan_get_result",
        "analytics_masterplan_summary": "analytics_masterplan_summary_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)


def _get_user_kpi_snapshot(*args, **kwargs):
    from apps.analytics.services.scoring.infinity_service import get_user_kpi_snapshot
    return get_user_kpi_snapshot(*args, **kwargs)


def _execute_infinity_orchestrator(*args, **kwargs):
    from apps.analytics.services.orchestration.infinity_orchestrator import execute
    return execute(*args, **kwargs)


def _get_latest_adjustment(*args, **kwargs):
    from apps.analytics.services.orchestration.infinity_loop import get_latest_adjustment
    return get_latest_adjustment(*args, **kwargs)


def _get_latest_adjustment_payload(*args, **kwargs):
    from apps.analytics.services.orchestration.infinity_loop import get_latest_adjustment, serialize_adjustment

    latest = get_latest_adjustment(*args, **kwargs)
    if latest is None:
        return None
    payload = dict(serialize_adjustment(latest) or {})
    payload.pop("id", None)
    return payload


def _scheduler_recalculate_all_scores() -> None:
    from AINDY.agents.autonomous_controller import evaluate_live_trigger, record_decision
    from AINDY.db.database import SessionLocal
    from AINDY.db.models.user import User
    from apps.analytics.services.orchestration.infinity_orchestrator import execute as execute_infinity_orchestrator

    try:
        db = SessionLocal()
    except Exception as exc:
        logger.warning("[Infinity Scheduler] DB unavailable: %s", exc)
        return
    try:
        trigger = {"trigger_type": "schedule", "source": "scheduler.infinity_scores", "goal": "daily_infinity_score_recalculation"}
        context = {"goal": "daily_infinity_score_recalculation", "importance": 0.60, "goal_alignment": 0.70}
        decision = evaluate_live_trigger(db=db, trigger=trigger, context=context)
        record_decision(db=db, trigger=trigger, evaluation=decision, trace_id=str(uuid.uuid4()), context=context)
        if decision["decision"] != "execute":
            logger.info("[Infinity Scheduler] Deferred by autonomy controller: %s", decision["reason"])
            return
        users = db.query(User).all()
        updated = 0
        for user in users:
            result = execute_infinity_orchestrator(user_id=str(user.id), db=db, trigger_event="scheduled")
            if result:
                updated += 1
        logger.info("[Infinity Scheduler] Recalculated scores for %d/%d users", updated, len(users))
    finally:
        db.close()


def _register_health_check() -> None:
    from AINDY.platform_layer.domain_health import domain_health_registry
    from AINDY.platform_layer.registry import register_health_check

    domain_health_registry.register("analytics", analytics_health_check)
    register_health_check("analytics", _check_health)


def analytics_health_check() -> bool:
    from AINDY.db.database import SessionLocal
    from apps.analytics.models import UserScore

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db.query(UserScore.id).limit(1).all()
        return True
    finally:
        db.close()


def _check_health() -> dict:
    try:
        from AINDY.config import settings as runtime_settings
        from apps.analytics.services.orchestration.infinity_orchestrator import execute
        from apps.analytics.services.scoring.kpi_weight_service import get_effective_weights

        _ = (
            execute,
            get_effective_weights,
            runtime_settings.FLOW_WAIT_TIMEOUT_MINUTES,
            runtime_settings.STUCK_RUN_THRESHOLD_MINUTES,
        )
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}



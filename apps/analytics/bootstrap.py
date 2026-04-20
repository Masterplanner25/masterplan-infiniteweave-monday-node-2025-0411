"""Analytics domain bootstrap."""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def register() -> None:
    _register_models()
    _register_routers()
    _register_response_adapters()
    _register_events()
    _register_jobs()
    _register_scheduled_jobs()
    _register_flow_results()


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
    from apps._adapters import raw_json_adapter

    register_response_adapter("analytics", raw_json_adapter)
    register_response_adapter("main", raw_json_adapter)


def _register_events() -> None:
    from AINDY.platform_layer.registry import register_event_handler, register_event_type
    from AINDY.core.system_event_types import SystemEventTypes

    register_event_type(SystemEventTypes.EXECUTION_COMPLETED)
    register_event_handler(SystemEventTypes.EXECUTION_COMPLETED, _handle_execution_completed)


def _handle_execution_completed(context: dict):
    db = context.get("db")
    result = None
    if db is not None and "execution_result" in context:
        from apps.masterplan.services.goal_service import update_goals_from_execution
        result = update_goals_from_execution(
            db,
            user_id=context.get("user_id"),
            workflow_type=context.get("workflow_type"),
            execution_result=context.get("execution_result"),
            success=context.get("success", True),
        )
    if db is not None and context.get("trigger_event") == "agent_completed" and context.get("user_id"):
        from apps.analytics.services.infinity_orchestrator import execute
        return execute(
            user_id=context["user_id"],
            trigger_event=context["trigger_event"],
            db=db,
        )
    return result


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job

    register_job("analytics.kpi_snapshot", _get_user_kpi_snapshot)
    register_job("analytics.infinity_execute", _execute_infinity_orchestrator)
    register_job("analytics.latest_adjustment", _get_latest_adjustment)
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
    from apps.analytics.services.infinity_service import get_user_kpi_snapshot
    return get_user_kpi_snapshot(*args, **kwargs)


def _execute_infinity_orchestrator(*args, **kwargs):
    from apps.analytics.services.infinity_orchestrator import execute
    return execute(*args, **kwargs)


def _get_latest_adjustment(*args, **kwargs):
    from apps.analytics.services.infinity_loop import get_latest_adjustment
    return get_latest_adjustment(*args, **kwargs)


def _scheduler_recalculate_all_scores() -> None:
    from AINDY.agents.autonomous_controller import evaluate_live_trigger, record_decision
    from AINDY.db.database import SessionLocal
    from AINDY.db.models.user import User
    from apps.analytics.services.infinity_orchestrator import execute as execute_infinity_orchestrator

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

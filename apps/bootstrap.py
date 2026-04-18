"""Application plugin registration for the AINDY platform."""

from __future__ import annotations

import logging
import uuid
from threading import Lock
from uuid import UUID

_BOOTSTRAPPED = False
_JOB_LOG_MIRROR_REGISTERED = False
logger = logging.getLogger(__name__)


def bootstrap_models() -> None:
    _register_models()
    _register_job_log_mirror()


def bootstrap() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    _register_models()
    _register_routers()
    _register_route_prefixes()
    _register_response_adapters()
    _register_execution_adapters()
    _register_startup_hooks()
    _register_events()
    _register_jobs()
    _register_scheduled_jobs()
    _register_agent_capabilities()
    _register_agent_tools()
    _register_agent_ranking()
    _register_trigger_evaluators()
    _register_flow_strategy()
    _register_agent_runtime_extensions()
    _register_async_jobs()
    _register_capture_rules()
    _register_flows()
    _register_flow_results()
    _register_flow_plans()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols

    import apps.analytics.models as analytics_models
    import apps.arm.models as arm_models
    import apps.authorship.models as authorship_models
    import apps.automation.models as automation_models
    import apps.freelance.models as freelance_models
    import apps.masterplan.models as masterplan_models
    import apps.rippletrace.models as rippletrace_models
    import apps.search.models as search_models
    import apps.tasks.models as tasks_models

    model_modules = (
        analytics_models,
        arm_models,
        authorship_models,
        automation_models,
        freelance_models,
        masterplan_models,
        rippletrace_models,
        search_models,
        tasks_models,
    )

    for module in model_modules:
        register_models(module.register_models)

    register_symbols(
        {
            name: value
            for module in model_modules
            for name, value in vars(module).items()
            if isinstance(value, type)
            and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_job_log_mirror() -> None:
    global _JOB_LOG_MIRROR_REGISTERED
    if _JOB_LOG_MIRROR_REGISTERED:
        return
    _JOB_LOG_MIRROR_REGISTERED = True

    from sqlalchemy import event
    from AINDY.db.models.job_log import JobLog
    from apps.automation.models import AutomationLog

    def _mirror_job_log(_mapper, connection, target: JobLog) -> None:
        table = AutomationLog.__table__
        values = {
            "id": str(target.id),
            "source": target.source,
            "task_name": target.task_name,
            "payload": target.payload,
            "status": target.status,
            "attempt_count": target.attempt_count,
            "max_attempts": target.max_attempts,
            "error_message": target.error_message,
            "user_id": target.user_id,
            "result": target.result,
            "trace_id": target.trace_id,
            "started_at": target.started_at,
            "completed_at": target.completed_at,
            "created_at": target.created_at,
            "scheduled_for": target.scheduled_for,
        }
        values = {key: value for key, value in values.items() if key in table.c}
        exists = connection.execute(
            table.select().with_only_columns(table.c.id).where(table.c.id == str(target.id))
        ).first()
        if exists:
            connection.execute(table.update().where(table.c.id == str(target.id)).values(**values))
        else:
            connection.execute(table.insert().values(**values))

    event.listen(JobLog, "after_insert", _mirror_job_log)
    event.listen(JobLog, "after_update", _mirror_job_log)


def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.agent.routes.agent_router import router as agent_router
    from apps.analytics.routes.analytics_router import router as analytics_router
    from apps.analytics.routes.main_router import legacy_router as legacy_main_router
    from apps.analytics.routes.main_router import router as main_router
    from apps.arm.routes.arm_router import router as arm_router
    from apps.authorship.routes.authorship_router import router as authorship_router
    from apps.automation.routes.automation_router import router as automation_router
    from apps.autonomy.routes.autonomy_router import router as autonomy_router
    from apps.bridge.routes.bridge_router import router as bridge_router
    from apps.dashboard.routes.dashboard_router import router as dashboard_router
    from apps.dashboard.routes.health_dashboard_router import router as health_dashboard_router
    from apps.freelance.routes.freelance_router import router as freelance_router
    from apps.identity.routes.identity_router import router as identity_router
    from apps.masterplan.routes.genesis_router import router as genesis_router
    from apps.masterplan.routes.goals_router import router as goals_router
    from apps.masterplan.routes.masterplan_router import router as masterplan_router
    from apps.masterplan.routes.score_router import router as score_router
    from apps.network_bridge.routes.network_bridge_router import router as network_bridge_router
    from apps.rippletrace.routes.legacy_surface_router import router as legacy_surface_router
    from apps.rippletrace.routes.rippletrace_router import router as rippletrace_router
    from apps.search.routes.leadgen_router import router as leadgen_router
    from apps.search.routes.research_results_router import router as research_router
    from apps.search.routes.research_results_router import search_history_router
    from apps.search.routes.seo_routes import router as seo_router
    from apps.social.routes.social_router import router as social_router
    from apps.tasks.routes.task_router import router as task_router
    from AINDY.routes.db_verify_router import router as db_verify_router
    from AINDY.routes.watcher_router import router as watcher_router

    for router in (
        agent_router,
        analytics_router,
        main_router,
        arm_router,
        authorship_router,
        automation_router,
        autonomy_router,
        bridge_router,
        dashboard_router,
        health_dashboard_router,
        freelance_router,
        identity_router,
        genesis_router,
        goals_router,
        masterplan_router,
        score_router,
        network_bridge_router,
        rippletrace_router,
        leadgen_router,
        research_router,
        search_history_router,
        seo_router,
        social_router,
        task_router,
    ):
        register_router(router)

    register_router(legacy_surface_router)
    register_router(legacy_main_router, legacy_root=True)
    register_router(db_verify_router, legacy_root=True)
    register_router(watcher_router, legacy_root=True)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix

    for prefix, execution_unit_type in {
        "agent": "agent",
        "arm": "flow",
        "automation": "job",
        "dashboard": "task",
        "genesis": "flow",
        "leadgen": "flow",
        "masterplan": "flow",
        "score": "task",
        "task": "task",
        "watcher": "task",
    }.items():
        register_route_prefix(prefix, execution_unit_type)


def _register_response_adapters() -> None:
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    from AINDY.core.execution_envelope import success as legacy_success
    from AINDY.platform_layer.registry import register_response_adapter

    def raw_json_adapter(*, route_name, canonical, status_code, trace_headers):
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(canonical.get("data")),
            headers=trace_headers,
        )

    def legacy_envelope_adapter(*, route_name, canonical, status_code, trace_headers):
        payload = canonical.get("data")
        if isinstance(payload, dict) and "status" in payload and "trace_id" in payload:
            body = payload
        else:
            body = legacy_success(
                payload,
                canonical.get("metadata", {}).get("events") or [],
                str(canonical.get("trace_id") or ""),
                next_action=canonical.get("metadata", {}).get("next_action"),
            )
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(body),
            headers=trace_headers,
        )

    def raw_canonical_adapter(*, route_name, canonical, status_code, trace_headers):
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(canonical),
            headers=trace_headers,
        )

    def memory_execute_adapter(*, route_name, canonical, status_code, trace_headers):
        payload = canonical.get("data")
        if not isinstance(payload, dict):
            return raw_canonical_adapter(
                route_name=route_name,
                canonical=canonical,
                status_code=status_code,
                trace_headers=trace_headers,
            )
        merged = dict(payload)
        merged["status"] = canonical.get("status")
        merged["trace_id"] = canonical.get("trace_id")
        merged["data"] = payload
        metadata = canonical.get("metadata", {})
        if metadata.get("events") is not None:
            merged["events"] = metadata.get("events")
        if metadata.get("next_action") is not None:
            merged["next_action"] = metadata.get("next_action")
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(merged),
            headers=trace_headers,
        )

    def memory_completion_adapter(*, route_name, canonical, status_code, trace_headers):
        if canonical.get("status") == "error":
            error_status = canonical.get("metadata", {}).get("status_code") or status_code
            detail = canonical.get("metadata", {}).get("error", "Execution failed")
            return JSONResponse(
                status_code=int(error_status),
                content={"error": "http_error", "details": jsonable_encoder(detail)},
                headers=trace_headers,
            )
        return raw_canonical_adapter(
            route_name=route_name,
            canonical=canonical,
            status_code=status_code,
            trace_headers=trace_headers,
        )

    for prefix in (
        "auth", "analytics", "arm", "automation", "main",
        "authorship", "bridge", "db", "flow", "health", "leadgen",
        "masterplan", "network_bridge", "observability", "rippletrace",
        "score", "scores", "seo", "legacy_surface", "watcher",
    ):
        register_response_adapter(prefix, raw_json_adapter)

    register_response_adapter("social", legacy_envelope_adapter)
    register_response_adapter("memory", raw_json_adapter)
    register_response_adapter("memory.execute", memory_execute_adapter)
    register_response_adapter("memory.execute.complete", memory_completion_adapter)
    register_response_adapter("memory.nodus.execute", raw_canonical_adapter)
    for prefix in ("autonomy", "system", "coordination"):
        register_response_adapter(prefix, legacy_envelope_adapter)


def _register_execution_adapters() -> None:
    from AINDY.platform_layer.registry import register_execution_adapter
    from apps.tasks.adapters import register as register_task_adapters

    register_task_adapters(register_execution_adapter)


def _register_startup_hooks() -> None:
    from AINDY.platform_layer.registry import register_startup_hook
    from apps.authorship.bootstrap import register as register_authorship_bootstrap

    register_authorship_bootstrap(register_startup_hook)


def _register_events() -> None:
    from AINDY.platform_layer.event_service import register_event_handler
    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import register_event_handler as register_registry_event_handler
    from AINDY.platform_layer.registry import register_event_type
    from apps.freelance.events import FreelanceEventTypes
    from apps.masterplan.events import MasterplanEventTypes
    from apps.masterplan.services.watcher_events import register_masterplan_event_handlers
    from apps.tasks.events import TaskEventTypes

    register_masterplan_event_handlers()
    register_event_handler("auth.register.completed", _handle_auth_register_completed)
    register_event_type(SystemEventTypes.EXECUTION_COMPLETED)
    for lifecycle_event in ("system.startup", "system.shutdown", "scheduler.tick"):
        register_event_type(lifecycle_event)
    for event_group in (TaskEventTypes, MasterplanEventTypes, FreelanceEventTypes):
        for value in vars(event_group).values():
            if isinstance(value, str):
                register_event_type(value)
    register_registry_event_handler(SystemEventTypes.EXECUTION_COMPLETED, _handle_execution_completed)
    register_registry_event_handler("system.startup", _handle_system_startup)
    register_registry_event_handler("system.shutdown", _handle_system_shutdown)
    register_registry_event_handler("scheduler.tick", _handle_scheduler_tick)


def _handle_execution_completed(context: dict):
    db = context.get("db")
    result = None
    if db is not None and "execution_result" in context:
        result = _update_goals_from_execution(
            db,
            user_id=context.get("user_id"),
            workflow_type=context.get("workflow_type"),
            execution_result=context.get("execution_result"),
            success=context.get("success", True),
        )
    if db is not None and context.get("trigger_event") == "agent_completed" and context.get("user_id"):
        return _execute_infinity_orchestrator(
            user_id=context["user_id"],
            trigger_event=context["trigger_event"],
            db=db,
        )
    return result


def _handle_auth_register_completed(event: dict) -> None:
    from AINDY.db.models.user import User
    from AINDY.utils.uuid_utils import ensure_uuid
    from apps.identity.services.signup_initialization_service import initialize_signup_state

    db = event.get("db")
    if db is None:
        return
    user_id = event.get("user_id")
    if user_id is None:
        return
    user_id = ensure_uuid(user_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return
    initialize_signup_state(db=db, user=user)


def _handle_system_startup(context: dict):
    from apps.tasks.services import task_service

    return task_service.start_background_tasks(
        enable=context.get("enable", True),
        log=context.get("log"),
    )


def _handle_system_shutdown(context: dict):
    from apps.tasks.services import task_service

    return task_service.stop_background_tasks(log=context.get("log"))


def _handle_scheduler_tick(context: dict):
    from apps.tasks.services.task_service import is_background_leader

    return is_background_leader()


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job
    from apps.tasks.services import task_service as task_services

    register_job("tasks.background.start", task_services.start_background_tasks)
    register_job("tasks.background.stop", task_services.stop_background_tasks)
    register_job("scheduler.infinity_scores", _scheduler_recalculate_all_scores)
    register_job("scheduler.masterplan_eta", _scheduler_recalculate_all_etas)
    register_job("scheduler.reminders", _scheduler_check_reminders)
    register_job("scheduler.recurrence", _scheduler_check_task_recurrence)
    register_job("scheduler.lease_heartbeat", lambda: task_services._heartbeat_lease_job())
    register_job("arm.analyzer", _create_arm_analyzer)
    register_job("genesis.synthesize", _genesis_synthesize)
    register_job("genesis.audit", _genesis_audit)
    register_job("automation.execute", _automation_execute)
    register_job("freelance.generate_delivery", _freelance_generate_delivery)
    register_job("goals.rank", _rank_goals)
    register_job("goals.calculate_alignment", _calculate_goal_alignment)
    register_job("goals.update_from_execution", _update_goals_from_execution)
    register_job("analytics.kpi_snapshot", _get_user_kpi_snapshot)
    register_job("analytics.infinity_execute", _execute_infinity_orchestrator)
    register_job("analytics.latest_adjustment", _get_latest_adjustment)
    register_job("tasks.background.is_leader", _is_background_leader)


def _register_scheduled_jobs() -> None:
    from AINDY.platform_layer.registry import register_scheduled_job
    from apps.tasks.services import task_service as task_services

    register_scheduled_job(
        "task_reminder_check",
        _scheduler_check_reminders,
        name="Task reminder check",
        trigger="interval",
        trigger_kwargs={"minutes": 1},
    )
    register_scheduled_job(
        "task_recurrence_check",
        _scheduler_check_task_recurrence,
        name="Task recurrence check",
        trigger="cron",
        trigger_kwargs={"hour": "*/6"},
    )
    register_scheduled_job(
        "daily_eta_recalculation",
        _scheduler_recalculate_all_etas,
        name="Daily ETA projection recalculation",
        trigger="cron",
        trigger_kwargs={"hour": 6},
    )
    register_scheduled_job(
        "daily_infinity_score_recalculation",
        _scheduler_recalculate_all_scores,
        name="Daily Infinity score recalculation",
        trigger="cron",
        trigger_kwargs={"hour": 7},
    )
    register_scheduled_job(
        "background_lease_heartbeat",
        lambda: task_services._heartbeat_lease_job(),
        name="Background task lease heartbeat",
        trigger="interval",
        trigger_kwargs={"seconds": 60},
    )


def _register_agent_runtime_extensions() -> None:
    from apps.agent.agents.runtime_extensions import register

    register()


def _register_agent_tools() -> None:
    from apps.agent.agents.tools import register as register_agent_tools
    from apps.arm.agents.tools import register as register_arm_tools
    from apps.masterplan.agents.tools import register as register_masterplan_tools
    from apps.search.agents.tools import register as register_search_tools
    from apps.tasks.agents.tools import register as register_task_tools

    register_agent_tools()
    register_arm_tools()
    register_masterplan_tools()
    register_search_tools()
    register_task_tools()


def _register_agent_capabilities() -> None:
    from apps.agent.agents.capabilities import register as register_agent_capabilities
    from apps.arm.agents.capabilities import register as register_arm_capabilities
    from apps.masterplan.agents.capabilities import register as register_masterplan_capabilities
    from apps.search.agents.capabilities import register as register_search_capabilities
    from apps.tasks.agents.capabilities import register as register_task_capabilities

    register_agent_capabilities()
    register_arm_capabilities()
    register_masterplan_capabilities()
    register_search_capabilities()
    register_task_capabilities()


def _register_agent_ranking() -> None:
    from apps.masterplan.agents.ranking import register

    register()


def _register_trigger_evaluators() -> None:
    from apps.agent.agents.triggers import register

    register()


def _register_flow_strategy() -> None:
    from AINDY.platform_layer.registry import register_flow_strategy
    from apps.rippletrace.flow_strategy import register

    register(register_flow_strategy)


def _create_arm_analyzer():
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    return DeepSeekCodeAnalyzer()


def _genesis_synthesize(*args, **kwargs):
    from apps.masterplan.services.genesis_ai import call_genesis_synthesis_llm

    return call_genesis_synthesis_llm(*args, **kwargs)


def _genesis_audit(*args, **kwargs):
    from apps.masterplan.services.genesis_ai import validate_draft_integrity

    return validate_draft_integrity(*args, **kwargs)


def _automation_execute(payload, db):
    from apps.automation.services.automation_execution_service import execute_automation_action

    return execute_automation_action(payload, db)


def _freelance_generate_delivery(*, db, order_id, user_id=None):
    from apps.freelance.services.freelance_service import generate_deliverable

    return generate_deliverable(db=db, order_id=order_id, user_id=user_id)


def _rank_goals(*args, **kwargs):
    from apps.masterplan.services.goal_service import rank_goals

    return rank_goals(*args, **kwargs)


def _calculate_goal_alignment(*args, **kwargs):
    from apps.masterplan.services.goal_service import calculate_goal_alignment

    return calculate_goal_alignment(*args, **kwargs)


def _update_goals_from_execution(*args, **kwargs):
    from apps.masterplan.services.goal_service import update_goals_from_execution

    return update_goals_from_execution(*args, **kwargs)


def _get_user_kpi_snapshot(*args, **kwargs):
    from apps.analytics.services.infinity_service import get_user_kpi_snapshot

    return get_user_kpi_snapshot(*args, **kwargs)


def _execute_infinity_orchestrator(*args, **kwargs):
    from apps.analytics.services.infinity_orchestrator import execute

    return execute(*args, **kwargs)


def _get_latest_adjustment(*args, **kwargs):
    from apps.analytics.services.infinity_loop import get_latest_adjustment

    return get_latest_adjustment(*args, **kwargs)


def _is_background_leader(*args, **kwargs):
    from apps.tasks.services.task_service import is_background_leader

    return is_background_leader(*args, **kwargs)


_ANALYZER = None
_ANALYZER_LOCK = Lock()


def _get_analyzer():
    global _ANALYZER
    if _ANALYZER is None:
        with _ANALYZER_LOCK:
            if _ANALYZER is None:
                _ANALYZER = _create_arm_analyzer()
    return _ANALYZER


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job

    register_async_job("agent.create_run")(_job_agent_create_run)
    register_async_job("agent.approve_run")(_job_agent_approve_run)
    register_async_job("arm.analyze")(_job_arm_analyze)
    register_async_job("arm.generate")(_job_arm_generate)
    register_async_job("genesis.message")(_job_genesis_message)
    register_async_job("genesis.synthesize")(_job_genesis_synthesize)
    register_async_job("genesis.audit")(_job_genesis_audit)
    register_async_job("memory.nodus.execute")(_job_memory_nodus_execute)
    register_async_job("watcher.ingest")(_job_watcher_ingest)
    register_async_job("automation.execute")(_job_automation_execute)
    register_async_job("freelance.generate_delivery")(_job_freelance_generate_delivery)


def _job_agent_create_run(payload: dict, db):
    from AINDY.agents.agent_runtime import create_run, execute_run, to_execution_response

    user_id = payload["user_id"]
    run = create_run(goal=payload["goal"], user_id=user_id, db=db)
    if not run:
        raise RuntimeError("Failed to generate plan")
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
    return to_execution_response(run, db)


def _job_agent_approve_run(payload: dict, db):
    from AINDY.agents.agent_runtime import approve_run, to_execution_response

    run = approve_run(run_id=payload["run_id"], user_id=payload["user_id"], db=db)
    if not run:
        raise RuntimeError("Run not found or not approvable")
    return to_execution_response(run, db)


def _job_arm_analyze(payload: dict, db):
    analyzer = _get_analyzer()
    return analyzer.run_analysis(
        file_path=payload["file_path"],
        user_id=payload["user_id"],
        db=db,
        complexity=payload.get("complexity"),
        urgency=payload.get("urgency"),
        additional_context=payload.get("context", ""),
    )


def _job_arm_generate(payload: dict, db):
    analyzer = _get_analyzer()
    return analyzer.generate_code(
        prompt=payload["prompt"],
        user_id=payload["user_id"],
        db=db,
        original_code=payload.get("original_code", ""),
        language=payload.get("language", "python"),
        generation_type=payload.get("generation_type", "generate"),
        analysis_id=payload.get("analysis_id"),
        complexity=payload.get("complexity"),
        urgency=payload.get("urgency"),
    )


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

    draft = _genesis_synthesize(
        session.summarized_state or {},
        user_id=str(user_id),
        db=db,
    )
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


def _job_memory_nodus_execute(payload: dict, db):
    from AINDY.runtime.nodus_execution_service import execute_nodus_task_payload

    return execute_nodus_task_payload(
        task_name=payload["task_name"],
        task_code=payload["task_code"],
        db=db,
        user_id=payload["user_id"],
        session_tags=payload.get("session_tags"),
        allowed_operations=payload.get("allowed_operations"),
        execution_id=payload.get("execution_id"),
        capability_token=payload.get("capability_token"),
    )


def _job_watcher_ingest(payload: dict, db):
    from AINDY.runtime.flow_engine import execute_intent

    return execute_intent(
        intent_data={
            "workflow_type": "watcher_ingest",
            "signals": payload["signals"],
        },
        db=db,
        user_id=payload.get("user_id"),
    )


def _job_automation_execute(payload: dict, db):
    return _automation_execute(payload, db)


def _job_freelance_generate_delivery(payload: dict, db):
    return _freelance_generate_delivery(
        db=db,
        order_id=int(payload["order_id"]),
        user_id=payload.get("user_id"),
    )


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
            result = execute_infinity_orchestrator(
                user_id=str(user.id),
                db=db,
                trigger_event="scheduled",
            )
            if result:
                updated += 1
        logger.info(
            "[Infinity Scheduler] Recalculated scores for %d/%d users",
            updated, len(users)
        )
    finally:
        db.close()


def _register_capture_rules() -> None:
    from AINDY.platform_layer.registry import register_memory_policy
    from apps.arm.memory_policy import register as register_arm_memory_policy
    from apps.automation.memory_policy import register as register_automation_memory_policy
    from apps.masterplan.memory_policy import register as register_masterplan_memory_policy
    from apps.search.memory_policy import register as register_search_memory_policy
    from apps.tasks.memory_policy import register as register_tasks_memory_policy

    for register_policy in (
        register_arm_memory_policy,
        register_automation_memory_policy,
        register_masterplan_memory_policy,
        register_search_memory_policy,
        register_tasks_memory_policy,
    ):
        register_policy(register_memory_policy)


def _register_flows() -> None:
    from AINDY.platform_layer.registry import register_flow, register_symbols
    from apps.automation.flows import flow_definitions, flow_definitions_extended
    from apps.automation.syscalls import syscall_handlers

    register_flow(flow_definitions.register_all_flows)
    register_symbols(
        {
            name: value
            for module in (flow_definitions, flow_definitions_extended, syscall_handlers)
            for name, value in vars(module).items()
            if not name.startswith("__")
        }
    )

def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    register_flow_result(
        "task_completion",
        extractor=lambda state: {
            "task_result": state.get("task_result"),
            "orchestration": state.get("task_orchestration"),
        },
    )
    result_keys = {
        'genesis_message': 'genesis_response',
        'memory_execution': 'memory_execution_response',
        'watcher_ingest': 'watcher_ingest_result',
        'arm_analysis': 'analysis_result',
        'arm_generate': 'generation_result',
        'leadgen_search': 'search_results',
        'task_create': 'task_create_result',
        'task_start': 'task_start_result',
        'task_pause': 'task_pause_result',
        'goal_create': 'goal_create_result',
        'score_recalculate': 'score_recalculate_result',
        'score_feedback': 'score_feedback_result',
        'arm_logs': 'arm_logs_result',
        'arm_config_get': 'arm_config_get_result',
        'arm_config_update': 'arm_config_update_result',
        'arm_metrics': 'arm_metrics_result',
        'arm_config_suggest': 'arm_config_suggest_result',
        'goals_list': 'goals_list_result',
        'goals_state': 'goals_state_result',
        'score_get': 'score_get_result',
        'score_history': 'score_history_result',
        'score_feedback_list': 'score_feedback_list_result',
        'leadgen_list': 'leadgen_list_result',
        'leadgen_preview_search': 'leadgen_preview_search_result',
        'tasks_list': 'tasks_list_result',
        'tasks_recurrence_check': 'tasks_recurrence_check_result',
        'agent_run_create': 'agent_run_create_result',
        'agent_runs_list': 'agent_runs_list_result',
        'agent_run_get': 'agent_run_get_result',
        'agent_run_approve': 'agent_run_approve_result',
        'agent_run_reject': 'agent_run_reject_result',
        'agent_run_recover': 'agent_run_recover_result',
        'agent_run_replay': 'agent_run_replay_result',
        'agent_run_steps': 'agent_run_steps_result',
        'agent_run_events': 'agent_run_events_result',
        'agent_tools_list': 'agent_tools_list_result',
        'agent_trust_get': 'agent_trust_get_result',
        'agent_trust_update': 'agent_trust_update_result',
        'agent_suggestions_get': 'agent_suggestions_get_result',
        'analytics_linkedin_ingest': 'analytics_linkedin_ingest_result',
        'analytics_masterplan_get': 'analytics_masterplan_get_result',
        'analytics_masterplan_summary': 'analytics_masterplan_summary_result',
        'watcher_signals_receive': 'watcher_ingest_result',
        'watcher_signals_list': 'watcher_signals_list_result',
        'genesis_session_create': 'genesis_session_create_result',
        'genesis_session_get': 'genesis_session_get_result',
        'genesis_draft_get': 'genesis_draft_get_result',
        'genesis_synthesize': 'genesis_synthesize_result',
        'genesis_audit': 'genesis_audit_result',
        'genesis_lock': 'genesis_lock_result',
        'genesis_activate': 'genesis_activate_result',
        'flow_runs_list': 'flow_runs_list_result',
        'flow_run_get': 'flow_run_get_result',
        'flow_run_history': 'flow_run_history_result',
        'flow_run_resume': 'flow_run_resume_result',
        'flow_registry_get': 'flow_registry_get_result',
        'memory_node_create': 'memory_node_create_result',
        'memory_node_get': 'memory_node_get_result',
        'memory_node_update': 'memory_node_update_result',
        'memory_node_history': 'memory_node_history_result',
        'memory_node_links': 'memory_node_links_result',
        'memory_nodes_search_tags': 'memory_nodes_search_tags_result',
        'memory_link_create': 'memory_link_create_result',
        'memory_node_traverse': 'memory_node_traverse_result',
        'memory_nodes_expand': 'memory_nodes_expand_result',
        'memory_nodes_search_similar': 'memory_nodes_search_similar_result',
        'memory_recall': 'memory_recall_result',
        'memory_recall_v3': 'memory_recall_v3_result',
        'memory_recall_federated': 'memory_recall_federated_result',
        'memory_agents_list': 'memory_agents_list_result',
        'memory_node_share': 'memory_node_share_result',
        'memory_agent_recall': 'memory_agent_recall_result',
        'memory_node_feedback': 'memory_node_feedback_result',
        'memory_node_performance': 'memory_node_performance_result',
        'memory_suggest': 'memory_suggest_result',
        'memory_nodus_execute': 'memory_nodus_execute_result',
        'memory_execute_loop': 'memory_execution_response',
        'nodus_execute': 'nodus_execute_result',
        'automation_logs_list': 'automation_logs_list_result',
        'automation_log_get': 'automation_log_get_result',
        'automation_log_replay': 'automation_log_replay_result',
        'automation_scheduler_status': 'automation_scheduler_status_result',
        'automation_task_trigger': 'automation_task_trigger_result',
        'freelance_order_create': 'freelance_order_create_result',
        'freelance_order_deliver': 'freelance_order_deliver_result',
        'freelance_delivery_update': 'freelance_delivery_update_result',
        'freelance_feedback_collect': 'freelance_feedback_collect_result',
        'freelance_orders_list': 'freelance_orders_list_result',
        'freelance_feedback_list': 'freelance_feedback_list_result',
        'freelance_metrics_latest': 'freelance_metrics_latest_result',
        'freelance_metrics_update': 'freelance_metrics_update_result',
        'freelance_delivery_generate': 'freelance_delivery_generate_result',
        'research_create': 'research_create_result',
        'research_list': 'research_list_result',
        'research_query': 'research_query_result',
        'search_history_list': 'search_history_list_result',
        'search_history_get': 'search_history_get_result',
        'search_history_delete': 'search_history_delete_result',
        'masterplan_lock_from_genesis': 'masterplan_lock_from_genesis_result',
        'masterplan_lock': 'masterplan_lock_result',
        'masterplan_list': 'masterplan_list_result',
        'masterplan_get': 'masterplan_get_result',
        'masterplan_anchor': 'masterplan_anchor_result',
        'masterplan_projection': 'masterplan_projection_result',
        'masterplan_activate': 'masterplan_activate_result',
        'autonomy_decisions_list': 'autonomy_decisions_list_result',
        'watcher_evaluate_trigger': 'watcher_evaluate_trigger_result',
        'dashboard_overview': 'dashboard_overview_result',
        'health_dashboard_list': 'health_dashboard_list_result',
        'observability_scheduler_status': 'observability_scheduler_status_result',
        'observability_requests': 'observability_requests_result',
        'observability_dashboard': 'observability_dashboard_result',
        'observability_execution_graph': 'observability_rippletrace_result',
        'observability_rippletrace': 'observability_rippletrace_result',
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

    completion_events = {
        "arm_analysis": "arm_analysis_complete",
        "task_completion": "task_completed",
        "leadgen_search": "leadgen_search",
        "genesis_conversation": "genesis_synthesized",
    }
    for flow_name, event_type in completion_events.items():
        register_flow_result(flow_name, completion_event=event_type)


def _register_flow_plans() -> None:
    from AINDY.platform_layer.registry import register_flow_plan

    plans = {
        "arm_analysis": {"steps": ["arm_validate_input", "arm_analyze_code", "arm_store_result"]},
        "arm_generation": {"steps": ["validate_input", "generate_code", "store_result"]},
        "genesis_conversation": {"steps": ["process_message", "store_insight"]},
        "genesis_message": {
            "steps": ["genesis_message_validate", "genesis_message_execute", "genesis_message_orchestrate"]
        },
        "genesis_lock": {"steps": ["validate_draft", "lock_masterplan", "store_decision"]},
        "task_completion": {"steps": ["task_validate", "task_complete", "task_orchestrate"]},
        "memory_execution": {
            "steps": ["memory_execution_validate", "memory_execution_run", "memory_execution_orchestrate"]
        },
        "watcher_ingest": {
            "steps": ["watcher_ingest_validate", "watcher_ingest_persist", "watcher_ingest_orchestrate"]
        },
        "leadgen_search": {"steps": ["leadgen_validate", "leadgen_search", "leadgen_store"]},
        "generic": {"steps": ["execute", "store_result"]},
    }
    for flow_name, plan in plans.items():
        register_flow_plan(flow_name, plan)


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


def _scheduler_check_reminders() -> None:
    from AINDY.agents.autonomous_controller import evaluate_live_trigger, record_decision
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import check_reminders

    try:
        db = SessionLocal()
    except Exception as exc:
        logger.warning("[Task Scheduler] DB unavailable: %s", exc)
        return
    try:
        trigger = {"trigger_type": "schedule", "source": "scheduler.reminders", "goal": "task_reminder_check"}
        context = {"goal": "task_reminder_check", "importance": 0.45}
        decision = evaluate_live_trigger(db=db, trigger=trigger, context=context)
        record_decision(db=db, trigger=trigger, evaluation=decision, trace_id=str(uuid.uuid4()), context=context)
        if decision["decision"] == "execute":
            check_reminders()
    finally:
        db.close()


def _scheduler_check_task_recurrence() -> None:
    from AINDY.agents.autonomous_controller import evaluate_live_trigger, record_decision
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import handle_recurrence

    try:
        db = SessionLocal()
    except Exception as exc:
        logger.warning("[Task Scheduler] DB unavailable: %s", exc)
        return
    try:
        trigger = {"trigger_type": "schedule", "source": "scheduler.recurrence", "goal": "task_recurrence_check"}
        context = {"goal": "task_recurrence_check", "importance": 0.40}
        decision = evaluate_live_trigger(db=db, trigger=trigger, context=context)
        record_decision(db=db, trigger=trigger, evaluation=decision, trace_id=str(uuid.uuid4()), context=context)
        if decision["decision"] == "execute":
            handle_recurrence()
    finally:
        db.close()

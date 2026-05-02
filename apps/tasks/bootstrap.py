"""Tasks domain bootstrap."""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

BOOTSTRAP_DEPENDS_ON: list[str] = []
IS_CORE_DOMAIN: bool = True
APP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_models()
    _register_router()
    _register_route_prefixes()
    _register_response_adapters()
    _register_execution_adapters()
    _register_events()
    _register_jobs()
    _register_scheduled_jobs()
    _register_async_jobs()
    _register_agent_tools()
    _register_agent_capabilities()
    _register_syscalls()
    _register_capture_rules()
    _register_flows()
    _register_flow_results()
    _register_flow_plans()
    _register_required_flow_nodes()
    _register_required_syscalls()
    _register_health_check()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.tasks.models as tasks_models

    register_models(tasks_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(tasks_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.tasks.routes.task_router import router as task_router
    from AINDY.routes.watcher_router import router as watcher_router

    register_router(task_router)
    register_router(watcher_router, legacy_root=True)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix

    register_route_prefix("task", "task")
    register_route_prefix("watcher", "task")
    register_route_prefix("score", "task")


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter

    register_response_adapter("watcher", raw_json_adapter)


def _register_execution_adapters() -> None:
    from AINDY.platform_layer.registry import register_execution_adapter
    from apps.tasks.adapters import register as register_task_adapters

    register_task_adapters(register_execution_adapter)


def _register_events() -> None:
    from AINDY.platform_layer.event_service import register_event_handler as register_internal_event_handler
    from AINDY.platform_layer.registry import register_event_handler, register_event_type
    from apps.tasks.events import TaskEventTypes

    for lifecycle_event in ("system.startup", "system.shutdown", "scheduler.tick"):
        register_event_type(lifecycle_event)
    for value in vars(TaskEventTypes).values():
        if isinstance(value, str):
            register_event_type(value)

    register_event_handler("system.startup", _handle_system_startup)
    register_event_handler("system.shutdown", _handle_system_shutdown)
    register_event_handler("scheduler.tick", _handle_scheduler_tick)
    register_internal_event_handler(TaskEventTypes.TASK_COMPLETED, _handle_task_completed)


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


def _handle_task_completed(context: dict) -> None:
    payload = context.get("payload") or {}
    task_id = payload.get("task_id")
    user_id = context.get("user_id")
    if not task_id or not user_id:
        return
    try:
        from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

        ctx = SyscallContext(
            execution_unit_id=str(uuid.uuid4()),
            user_id=str(user_id),
            capabilities=["task.read", "masterplan.cascade_activate"],
            trace_id=context.get("trace_id", ""),
            metadata={},
        )
        task_result = get_dispatcher().dispatch(
            "sys.v1.task.get",
            {"task_id": int(task_id), "user_id": str(user_id)},
            ctx,
        )
        if task_result["status"] != "success":
            return
        task = ((task_result.get("data") or {}).get("task") or {})
        masterplan_id = task.get("masterplan_id")
        if not masterplan_id:
            return
        get_dispatcher().dispatch(
            "sys.v1.masterplan.cascade_activate",
            {"masterplan_id": str(masterplan_id), "user_id": str(user_id)},
            ctx,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "[cascade] task completion cascade failed (non-fatal): %s", exc
        )


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job
    from apps.tasks.services import task_service as task_services

    register_job("tasks.background.start", task_services.start_background_tasks)
    register_job("tasks.background.stop", task_services.stop_background_tasks)
    register_job("scheduler.reminders", _scheduler_check_reminders)
    register_job("scheduler.recurrence", _scheduler_check_task_recurrence)
    register_job("scheduler.lease_heartbeat", lambda: task_services._heartbeat_lease_job())
    register_job("tasks.background.is_leader", _is_background_leader)
    register_job("resume_watchdog.scan", _job_resume_watchdog)


def _register_scheduled_jobs() -> None:
    from AINDY.platform_layer.registry import register_scheduled_job
    from apps.tasks.services import task_service as task_services
    from AINDY.config import settings

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
        "background_lease_heartbeat",
        lambda: task_services._heartbeat_lease_job(),
        name="Background task lease heartbeat",
        trigger="interval",
        trigger_kwargs={"seconds": 60},
    )
    register_scheduled_job(
        "wait_recovery_poll",
        _job_wait_recovery_poll,
        name="WAIT recovery poll",
        trigger="interval",
        trigger_kwargs={"seconds": 60},
    )
    register_scheduled_job(
        "resume_watchdog",
        _job_resume_watchdog,
        name="Flow resume watchdog (Redis failure recovery)",
        trigger="interval",
        trigger_kwargs={"minutes": settings.AINDY_WATCHDOG_INTERVAL_MINUTES},
    )


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job

    register_async_job("watcher.ingest")(_job_watcher_ingest)


def _register_agent_tools() -> None:
    from apps.tasks.agents.tools import register as register_task_tools
    register_task_tools()


def _register_agent_capabilities() -> None:
    from apps.tasks.agents.capabilities import register as register_task_capabilities
    register_task_capabilities()


def _register_syscalls() -> None:
    from AINDY.platform_layer.registry import register_symbols
    from apps.tasks.syscalls import syscall_handlers

    register_symbols(
        {
            name: value
            for name, value in vars(syscall_handlers).items()
            if not name.startswith("__")
        }
    )
    syscall_handlers.register_task_syscall_handlers()


def _register_capture_rules() -> None:
    from AINDY.platform_layer.registry import register_memory_policy
    from apps.tasks.memory_policy import register as register_tasks_memory_policy
    register_tasks_memory_policy(register_memory_policy)


def _register_flows() -> None:
    from AINDY.platform_layer.registry import register_flow, register_symbols
    from apps.tasks.flows import tasks_flows

    register_symbols(
        {
            name: value
            for name, value in vars(tasks_flows).items()
            if not name.startswith("__")
        }
    )
    register_flow(tasks_flows.register)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "task_create": "task_create_result",
        "task_start": "task_start_result",
        "task_pause": "task_pause_result",
        "tasks_list": "tasks_list_result",
        "tasks_recurrence_check": "tasks_recurrence_check_result",
        "watcher_ingest": "watcher_ingest_result",
        "watcher_signals_receive": "watcher_ingest_result",
        "watcher_signals_list": "watcher_signals_list_result",
        "watcher_evaluate_trigger": "watcher_evaluate_trigger_result",
        "observability_scheduler_status": "observability_scheduler_status_result",
        "observability_requests": "observability_requests_result",
        "observability_dashboard": "observability_dashboard_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

    register_flow_result(
        "task_completion",
        extractor=lambda state: {
            "task_result": state.get("task_result"),
            "orchestration": state.get("task_orchestration"),
        },
    )
    register_flow_result("task_completion", completion_event="task_completed")


def _register_flow_plans() -> None:
    from AINDY.platform_layer.registry import register_flow_plan

    register_flow_plan(
        "task_completion",
        {"steps": ["task_validate", "task_complete", "task_orchestrate"]},
    )
    register_flow_plan(
        "watcher_ingest",
        {"steps": ["watcher_ingest_validate", "watcher_ingest_persist", "watcher_ingest_orchestrate"]},
    )


def _register_required_flow_nodes() -> None:
    from AINDY.platform_layer.registry import register_required_flow_node, register_symbols
    from apps.tasks.services.task_service import _BACKGROUND_LEASE_NAME

    register_required_flow_node("task_complete")
    register_symbols(
        {
            "task_background_lease_name": _BACKGROUND_LEASE_NAME,
            "task_is_background_leader": _task_is_background_leader,
        }
    )


def _register_required_syscalls() -> None:
    from AINDY.platform_layer.registry import register_required_syscall

    for name in (
        "sys.v1.task.create",
        "sys.v1.task.complete",
        "sys.v1.task.complete_full",
    ):
        register_required_syscall(name)


def _task_is_background_leader() -> bool:
    from apps.tasks.services.task_service import is_background_leader

    return is_background_leader()


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


def _job_wait_recovery_poll() -> None:
    from datetime import datetime, timedelta, timezone
    from AINDY.config import settings
    from AINDY.db.database import SessionLocal
    from AINDY.db.models.flow_run import FlowRun
    from AINDY.db.models.waiting_flow_run import WaitingFlowRun
    from AINDY.kernel.scheduler_engine import get_scheduler_engine

    db = None
    try:
        db = SessionLocal()
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(minutes=settings.STUCK_RUN_THRESHOLD_MINUTES)
        rows = db.query(WaitingFlowRun).all()
        scheduler = get_scheduler_engine()
        for row in rows:
            flow_run = db.query(FlowRun).filter(FlowRun.id == row.run_id).first()
            if flow_run is not None and flow_run.status not in ("waiting", "running"):
                db.delete(row)
                continue
            if (
                row.timeout_at
                and row.timeout_at < now
                and row.event_type == "__time_wait__"
                and row.max_wait_seconds is None
            ):
                scheduler.notify_event(row.event_type, correlation_id=row.correlation_id)
                continue
            if row.registered_at and row.registered_at < stale_cutoff:
                logger.warning(
                    "[WaitRecovery] unresolved waiting row run=%s event=%s age_minutes=%d instance=%s",
                    row.run_id,
                    row.event_type,
                    int((now - row.registered_at).total_seconds() // 60),
                    row.instance_id,
                )
        db.commit()
    except Exception as exc:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        try:
            from AINDY.platform_layer.metrics import wait_recovery_poll_failure_total

            wait_recovery_poll_failure_total.inc()
        except Exception:
            pass
        logger.error(
            "[wait_recovery_poll] Poll failed: %s - waiting flows may be stuck.",
            exc,
            exc_info=True,
        )
        if db is not None:
            try:
                from AINDY.core.observability_events import emit_recovery_failure

                emit_recovery_failure("wait_recovery_poll", exc, db, logger=logger)
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()


def _job_resume_watchdog() -> None:
    from AINDY.db.database import SessionLocal
    from AINDY.core.resume_watchdog import scan_and_resume_stranded_flows

    db = None
    try:
        db = SessionLocal()
        count = scan_and_resume_stranded_flows(db)
        if count:
            logger.info("[resume_watchdog] Resumed %d stranded flow(s)", count)
    except Exception as exc:
        logger.warning("[resume_watchdog] Job failed: %s", exc)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


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


def _is_background_leader(*args, **kwargs):
    from apps.tasks.services.task_service import is_background_leader
    return is_background_leader(*args, **kwargs)


def tasks_health_check() -> bool:
    from AINDY.db.database import SessionLocal

    try:
        from apps.tasks.models import Task
    except Exception as exc:
        raise RuntimeError(f"tasks health import failed: {exc}") from exc

    db = SessionLocal()
    try:
        db.query(Task.id).limit(1).all()
        return True
    finally:
        db.close()


def _register_health_check() -> None:
    from AINDY.platform_layer.domain_health import domain_health_registry
    from AINDY.platform_layer.registry import register_health_check

    domain_health_registry.register("tasks", tasks_health_check)
    register_health_check("tasks", _check_health)


def _check_health() -> dict:
    db = None
    try:
        from AINDY.db.database import SessionLocal
        from apps.tasks.models import Task

        db = SessionLocal()
        db.query(Task.id).limit(1).all()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}
    finally:
        if db is not None:
            db.close()

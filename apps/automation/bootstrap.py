"""Automation domain bootstrap."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MOVED_SYSCALL_SYMBOLS = {
    "_handle_task_create",
    "_handle_task_complete",
    "_handle_task_complete_full",
    "_handle_task_start",
    "_handle_task_pause",
    "_handle_task_orchestrate",
    "_handle_watcher_ingest",
}

_MOVED_FLOW_SYMBOLS = {
    "task_create_validate",
    "task_create_execute",
    "task_validate",
    "task_complete",
    "task_orchestrate",
    "task_start_execute",
    "task_pause_execute",
    "watcher_ingest_validate",
    "watcher_ingest_persist",
    "watcher_ingest_orchestrate",
}

BOOTSTRAP_DEPENDS_ON: list[str] = [
    "agent",
    "analytics",
    "arm",
    "masterplan",
    "tasks",
]
APP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_models()
    _register_router()
    _register_route_prefixes()
    _register_response_adapters()
    _register_events()
    _register_jobs()
    _register_async_jobs()
    _register_capture_rules()
    _register_flows()
    _register_flow_results()
    _register_flow_plans()
    _register_required_flow_nodes()
    _register_required_syscalls()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.automation.models as automation_models

    register_models(automation_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(automation_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.automation.routes.automation_router import router as automation_router
    register_router(automation_router)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix
    register_route_prefix("automation", "job")


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter
    register_response_adapter("automation", raw_json_adapter)


def _register_events() -> None:
    from AINDY.platform_layer.registry import register_event_handler
    register_event_handler("job_log.written", _handle_job_log_written)


def _handle_job_log_written(context: dict) -> None:
    log_id = context.get("job_log_id")
    if not log_id:
        return
    from AINDY.db.database import SessionLocal
    from AINDY.db.models.job_log import JobLog
    from apps.automation.services.job_log_sync_service import sync_job_log_to_automation_log

    db = SessionLocal()
    try:
        row = db.query(JobLog).filter(JobLog.id == str(log_id)).first()
        if row is not None:
            sync_job_log_to_automation_log(db, row)
    except Exception as exc:
        logger.debug(
            "[AutomationBridge] job_log sync failed for %s: %s",
            log_id,
            exc,
        )
    finally:
        db.close()


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job
    register_job("automation.execute", _automation_execute)


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job
    register_async_job("automation.execute")(_job_automation_execute)


def _register_capture_rules() -> None:
    from AINDY.platform_layer.registry import register_memory_policy
    from apps.automation.memory_policy import register as register_automation_memory_policy
    register_automation_memory_policy(register_memory_policy)


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
            if (
                not name.startswith("__")
                and name not in _MOVED_SYSCALL_SYMBOLS
                and name not in _MOVED_FLOW_SYMBOLS
            )
        }
    )


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "automation_logs_list": "automation_logs_list_result",
        "automation_log_get": "automation_log_get_result",
        "automation_log_replay": "automation_log_replay_result",
        "automation_scheduler_status": "automation_scheduler_status_result",
        "automation_task_trigger": "automation_task_trigger_result",
        "memory_execution": "memory_execution_response",
        "memory_execute_loop": "memory_execution_response",
        "nodus_execute": "nodus_execute_result",
        "memory_nodus_execute": "memory_nodus_execute_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)


def _register_flow_plans() -> None:
    from AINDY.platform_layer.registry import register_flow_plan

    register_flow_plan(
        "memory_execution",
        {"steps": ["memory_execution_validate", "memory_execution_run", "memory_execution_orchestrate"]},
    )
    register_flow_plan("generic", {"steps": ["execute", "store_result"]})


def _register_required_flow_nodes() -> None:
    from AINDY.platform_layer.registry import register_required_flow_node

    register_required_flow_node("memory_execution_validate")


def _register_required_syscalls() -> None:
    from AINDY.platform_layer.registry import register_required_syscall

    for name in (
        "sys.v1.score.feedback",
        "sys.v1.agent.suggest_tools",
    ):
        register_required_syscall(name)


def _automation_execute(payload, db):
    from apps.automation.services.automation_execution_service import execute_automation_action
    return execute_automation_action(payload, db)


def _job_automation_execute(payload: dict, db):
    return _automation_execute(payload, db)

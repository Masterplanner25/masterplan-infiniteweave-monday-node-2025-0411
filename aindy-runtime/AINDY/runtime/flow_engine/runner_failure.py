from AINDY.runtime.flow_engine.serialization import (
    _format_execution_response,
    _serialize_flow_events,
)
from AINDY.runtime.flow_engine.shared import SystemEventTypes, datetime, logger, timezone


def fail_execution(
    runner,
    run,
    state: dict,
    root_event_id: str | None,
    error_message: str,
    *,
    failed_node: str,
    parent_event_id: str | None = None,
) -> dict:
    run.status = "failed"
    run.waiting_for = None
    run.wait_deadline = None
    run.error_message = error_message
    run.error_detail = None
    run.completed_at = datetime.now(timezone.utc)
    runner.db.commit()
    try:
        from AINDY.core.execution_unit_service import ExecutionUnitService

        eus = ExecutionUnitService(runner.db)
        eu_id = getattr(runner, "_eu_id", None)
        if eu_id:
            eus.update_status(eu_id, "failed")
        else:
            eu = eus.get_by_source("flow_run", run.id)
            if eu:
                eus.update_status(eu.id, "failed")
        try:
            from AINDY.kernel.resource_manager import get_resource_manager as get_rm

            get_rm().mark_completed(
                getattr(runner, "_tenant_id", str(runner.user_id or "")),
                str(eu_id) if eu_id else None,
            )
        except Exception as exc:
            logger.debug(
                "[EU] resource_manager.mark_completed(failed) skipped: %s",
                exc,
            )
    except Exception as exc:
        logger.warning("[EU] flow fail hook - non-fatal | error=%s", exc)
    try:
        runner._emit_execution_failed(
            {
                "db": runner.db,
                "run_id": str(run.id),
                "trace_id": run.trace_id or str(run.id),
                "user_id": str(runner.user_id) if runner.user_id else None,
                "workflow_type": runner.workflow_type,
                "flow_name": run.flow_name,
                "error": error_message,
                "failed_node": failed_node,
                "success": False,
            }
        )
    except Exception as exc:
        logger.warning("Execution failure hook skipped: %s", exc)
    from AINDY.runtime import flow_engine as flow_engine_module

    flow_engine_module.emit_system_event(
        db=runner.db,
        event_type=SystemEventTypes.EXECUTION_FAILED,
        user_id=runner.user_id,
        trace_id=run.trace_id or str(run.id),
        parent_event_id=root_event_id,
        source="flow",
        payload={
            "run_id": str(run.id),
            "workflow_type": runner.workflow_type,
            "failed_node": failed_node,
            "error": error_message,
        },
        required=True,
    )
    flow_engine_module.emit_error_event(
        db=runner.db,
        error_type="execution",
        message=error_message,
        user_id=runner.user_id,
        trace_id=run.trace_id or str(run.id),
        parent_event_id=parent_event_id,
        source="flow",
        payload={
            "run_id": str(run.id),
            "workflow_type": runner.workflow_type,
            "failed_node": failed_node,
        },
        required=True,
    )
    return _format_execution_response(
        status="FAILED",
        trace_id=run.trace_id or str(run.id),
        result={"error": error_message, "failed_node": failed_node},
        events=_serialize_flow_events(runner.db, run.id),
        next_action=None,
        run_id=run.id,
        state=state,
    )

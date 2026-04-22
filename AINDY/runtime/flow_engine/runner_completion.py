from AINDY.runtime.flow_engine.serialization import (
    _extract_async_handoff,
    _extract_execution_result,
    _extract_next_action,
    _format_execution_response,
    _json_safe,
    _serialize_flow_events,
)
from AINDY.runtime.flow_engine.shared import (
    SystemEventTypes,
    datetime,
    logger,
    queue_memory_capture,
    timezone,
)


def maybe_finalize_completion(
    runner,
    run,
    state: dict,
    current_node: str,
    root_event_id,
    node_started_event_id,
):
    if current_node not in runner.flow.get("end", []):
        return None
    try:
        execution_result = _extract_execution_result(runner.workflow_type, state)
        handoff = _extract_async_handoff(execution_result)
        if handoff is not None:
            update_count = (
                runner.db.query(type(run))
                .filter(type(run).id == run.id)
                .update(
                    {
                        type(run).status: handoff["status"].lower(),
                        type(run).state: _json_safe(state),
                        type(run).current_node: current_node,
                        type(run).waiting_for: None,
                        type(run).wait_deadline: None,
                        type(run).job_log_id: handoff["job_log_id"] or run.job_log_id,
                    },
                    synchronize_session=False,
                )
            )
            if update_count != 1:
                raise RuntimeError(
                    f"FlowRun {run.id} not found during async handoff finalization"
                )
            run_id = run.id
            runner.db.commit()
            try:
                runner.db.expunge(run)
            except Exception:
                pass
            runner.db.expire_all()
            queued_run = runner.db.query(type(run)).filter(type(run).id == run_id).first()
            return _format_execution_response(
                status=handoff["status"],
                trace_id=queued_run.trace_id or str(queued_run.id),
                result=execution_result,
                events=_serialize_flow_events(runner.db, queued_run.id),
                next_action=_extract_next_action(execution_result),
                run_id=queued_run.id,
                state=state,
            )

        runner._capture_flow_completion(run, state)
        run.status = "success"
        run.state = _json_safe(state)
        run.waiting_for = None
        run.wait_deadline = None
        run.completed_at = datetime.now(timezone.utc)
        runner.db.commit()
        try:
            runner._emit_execution_completed(
                {
                    "db": runner.db,
                    "run_id": str(run.id),
                    "trace_id": run.trace_id or str(run.id),
                    "user_id": str(runner.user_id) if runner.user_id else None,
                    "workflow_type": runner.workflow_type,
                    "flow_name": run.flow_name,
                    "execution_result": execution_result,
                    "success": True,
                }
            )
        except Exception as exc:
            logger.warning("Execution completion hook skipped: %s", exc)
        from AINDY.runtime import flow_engine as flow_engine_module

        flow_engine_module.emit_system_event(
            db=runner.db,
            event_type=SystemEventTypes.EXECUTION_COMPLETED,
            user_id=runner.user_id,
            trace_id=run.trace_id or str(run.id),
            parent_event_id=root_event_id,
            source="flow",
            payload={
                "run_id": str(run.id),
                "workflow_type": runner.workflow_type,
                "result": execution_result,
            },
            required=True,
        )
        return _format_execution_response(
            status="SUCCESS",
            trace_id=run.trace_id or str(run.id),
            result=execution_result,
            events=_serialize_flow_events(runner.db, run.id),
            next_action=_extract_next_action(execution_result),
            run_id=run.id,
            state=state,
        )
    except Exception as exc:
        return runner._fail_execution(
            f"Completion finalization failed: {exc}",
            failed_node=current_node,
            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
        )


def capture_flow_completion(runner, run, state: dict) -> None:
    if not runner.user_id or not runner.workflow_type:
        return
    try:
        from AINDY.db.models.flow_run import FlowHistory

        history = (
            runner.db.query(FlowHistory)
            .filter(FlowHistory.flow_run_id == run.id)
            .order_by(FlowHistory.created_at.asc())
            .all()
        )
        if not history:
            return

        node_summary = " -> ".join(
            f"{item.node_name}({item.execution_time_ms or 0}ms)" for item in history
        )
        total_ms = sum(item.execution_time_ms or 0 for item in history)
        success_count = sum(1 for item in history if item.status == "SUCCESS")
        content = (
            f"Flow '{run.flow_name}' ({runner.workflow_type}) completed: "
            f"{node_summary}. "
            f"{success_count}/{len(history)} nodes succeeded, "
            f"{total_ms}ms total."
        )

        from AINDY.platform_layer.registry import get_flow_completion_event

        event_type = get_flow_completion_event(runner.workflow_type) or "flow_completion"
        namespace = runner.workflow_type.split("_")[0]
        queue_memory_capture(
            db=runner.db,
            user_id=runner.user_id,
            agent_namespace=namespace,
            event_type=event_type,
            content=content,
            source=f"flow_history:{run.flow_name}",
            tags=["flow_history", "execution_pattern", runner.workflow_type],
            context={"run_id": run.id, "total_ms": total_ms},
        )
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService

            eus = ExecutionUnitService(runner.db)
            eu_id = getattr(runner, "_eu_id", None)
            if eu_id:
                eus.update_status(eu_id, "completed")
            else:
                eu = eus.get_by_source("flow_run", run.id)
                if eu:
                    eus.update_status(eu.id, "completed")
            try:
                from AINDY.kernel.resource_manager import get_resource_manager as get_rm

                get_rm().mark_completed(
                    getattr(runner, "_tenant_id", str(runner.user_id or "")),
                    str(eu_id) if eu_id else None,
                )
            except Exception as exc:
                logger.debug(
                    "[EU] resource_manager.mark_completed(success) skipped: %s",
                    exc,
                )
        except Exception as exc:
            logger.warning("[EU] flow completion hook - non-fatal | error=%s", exc)
    except Exception as exc:
        logger.warning("FlowHistory -> Memory Bridge capture failed: %s", exc)
        from AINDY.runtime import flow_engine as flow_engine_module

        flow_engine_module.emit_error_event(
            db=runner.db,
            error_type="memory_capture",
            message=str(exc),
            user_id=runner.user_id,
            trace_id=run.trace_id,
            parent_event_id=state.get("root_event_id") if isinstance(state, dict) else None,
            source="flow",
            payload={"run_id": str(run.id), "workflow_type": runner.workflow_type},
            required=True,
        )

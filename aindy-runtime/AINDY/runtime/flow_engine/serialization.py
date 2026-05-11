from AINDY.runtime.flow_engine.shared import (
    Any,
    Optional,
    Session,
    date,
    datetime,
    execution_error,
    execution_success,
    uuid,
)


def _json_safe(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _serialize_flow_events(db: Session, run_id) -> list[dict]:
    from AINDY.db.models.flow_run import FlowHistory

    history = (
        db.query(FlowHistory)
        .filter(FlowHistory.flow_run_id == run_id)
        .order_by(FlowHistory.created_at.asc(), FlowHistory.id.asc())
        .all()
    )
    return [
        {
            "type": "flow.node",
            "node": item.node_name,
            "status": item.status,
            "execution_time_ms": item.execution_time_ms,
            "error": item.error_message,
            "timestamp": item.created_at.isoformat() if item.created_at else None,
        }
        for item in history
    ]


def _extract_execution_result(workflow_type: str | None, state: dict) -> object:
    if not isinstance(state, dict):
        return state

    from AINDY.platform_layer.registry import (
        get_flow_result_extractor,
        get_flow_result_key,
    )

    workflow_name = workflow_type or ""
    extractor = get_flow_result_extractor(workflow_name)
    if extractor is not None:
        return extractor(state)

    result_key = get_flow_result_key(workflow_name)
    if result_key and result_key in state:
        return state.get(result_key)
    return state


def _extract_next_action(result: object) -> Optional[str]:
    if not isinstance(result, dict):
        return None

    direct = result.get("next_action")
    if direct:
        return direct

    orchestration = result.get("orchestration")
    if isinstance(orchestration, dict):
        nested = orchestration.get("next_action")
        if nested:
            return nested
    return None


def _extract_async_handoff(result: object) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    response = None
    handoff_status = None
    if result.get("_http_status") == 202 and isinstance(result.get("_http_response"), dict):
        response = result["_http_response"]
        handoff_status = str(response.get("status") or "QUEUED").upper()
    else:
        status = str(result.get("status") or "").upper()
        if status in {"QUEUED", "DEFERRED"}:
            response = result
            handoff_status = status

    if not isinstance(response, dict) or handoff_status is None:
        return None

    data = response.get("data")
    nested_result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(nested_result, dict):
        nested_result = {}

    job_log_id = (
        nested_result.get("job_log_id")
        or (data.get("job_log_id") if isinstance(data, dict) else None)
        or response.get("job_log_id")
    )
    return {
        "status": handoff_status,
        "response": response,
        "job_log_id": job_log_id,
    }


def _format_execution_response(
    *,
    status: str,
    trace_id: str,
    result: object = None,
    events: Optional[list[dict]] = None,
    next_action: Optional[str] = None,
    run_id: object = None,
    state: Optional[dict] = None,
) -> dict:
    from AINDY.core.execution_record_service import build_execution_record

    if str(status).upper() == "ERROR":
        response = execution_error(
            message=(
                result.get("message")
                if isinstance(result, dict) and result.get("message")
                else str(result or "Execution failed")
            ),
            events=events,
            trace_id=trace_id,
        )
    else:
        response = execution_success(
            result=result,
            events=events,
            trace_id=trace_id,
            next_action=next_action,
        )
        response["status"] = status

    response["run_id"] = str(run_id) if run_id is not None else None
    response["state"] = state if isinstance(state, dict) else None
    workflow_type = state.get("workflow_type") if isinstance(state, dict) else None
    result_summary = (
        result
        if isinstance(result, (dict, list, str, int, float, bool)) or result is None
        else str(result)
    )
    response["execution_record"] = build_execution_record(
        run_id=str(run_id) if run_id is not None else None,
        trace_id=trace_id,
        execution_unit_id=str(run_id) if run_id is not None else trace_id,
        workflow_type=workflow_type,
        status=str(status).lower() if status is not None else None,
        error=(result.get("message") if isinstance(result, dict) else None)
        if str(status).upper() == "ERROR"
        else None,
        actor="flow",
        source="flow",
        result_summary=result_summary,
        correlation_id=trace_id,
    )
    return response

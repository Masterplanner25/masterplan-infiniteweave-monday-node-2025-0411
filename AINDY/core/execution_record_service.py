from __future__ import annotations

from typing import Any

from AINDY.core.execution_unit_service import ExecutionUnitService


def build_execution_record(
    *,
    run_id: str | None = None,
    trace_id: str | None = None,
    execution_unit_id: str | None = None,
    parent_run_id: str | None = None,
    workflow_type: str | None = None,
    status: str | None = None,
    error: str | None = None,
    actor: str | None = None,
    source: str | None = None,
    result_summary: Any = None,
    correlation_id: str | None = None,
    execution_unit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unit = dict(execution_unit or {})
    return {
        "run_id": run_id,
        "trace_id": trace_id or run_id,
        "execution_unit_id": execution_unit_id or unit.get("id") or run_id,
        "parent_run_id": parent_run_id,
        "workflow_type": workflow_type or unit.get("extra", {}).get("workflow_type"),
        "status": status,
        "error": error,
        "actor": actor,
        "source": source,
        "correlation_id": correlation_id or unit.get("correlation_id"),
        "result_summary": result_summary,
        "execution_unit": unit or None,
    }


def record_from_flow_run(flow_run, *, status: str | None = None, error: str | None = None, result_summary: Any = None) -> dict[str, Any]:
    unit = ExecutionUnitService.view_from_flow_run(flow_run)
    return build_execution_record(
        run_id=str(getattr(flow_run, "id", None) or ""),
        trace_id=getattr(flow_run, "trace_id", None),
        execution_unit_id=str(getattr(flow_run, "id", None) or ""),
        workflow_type=getattr(flow_run, "workflow_type", None),
        status=status or getattr(flow_run, "status", None),
        error=error or getattr(flow_run, "error_message", None),
        actor="flow",
        source="flow",
        result_summary=result_summary,
        execution_unit=unit,
    )


def record_from_agent_run(agent_run, *, result_summary: Any = None) -> dict[str, Any]:
    unit = ExecutionUnitService.view_from_agent_run(agent_run)
    return build_execution_record(
        run_id=str(getattr(agent_run, "id", None) or ""),
        trace_id=getattr(agent_run, "trace_id", None),
        execution_unit_id=str(getattr(agent_run, "flow_run_id", None) or getattr(agent_run, "id", None) or ""),
        parent_run_id=str(getattr(agent_run, "replayed_from_run_id", None) or "") or None,
        workflow_type="agent_execution",
        status=getattr(agent_run, "status", None),
        error=getattr(agent_run, "error_message", None),
        actor="agent",
        source="agent",
        result_summary=result_summary if result_summary is not None else getattr(agent_run, "result", None),
        correlation_id=getattr(agent_run, "correlation_id", None),
        execution_unit=unit,
    )


def record_from_job_log(log, *, workflow_type: str | None = None, actor: str = "async", source: str | None = None, result_summary: Any = None, execution_unit: dict[str, Any] | None = None) -> dict[str, Any]:
    unit = execution_unit or ExecutionUnitService.view_from_job_log(log)
    return build_execution_record(
        run_id=str(getattr(log, "id", None) or ""),
        trace_id=getattr(log, "trace_id", None) or str(getattr(log, "id", None) or ""),
        execution_unit_id=str(getattr(log, "id", None) or ""),
        workflow_type=workflow_type,
        status=getattr(log, "status", None),
        error=getattr(log, "error_message", None),
        actor=actor,
        source=source or getattr(log, "source", None),
        result_summary=result_summary if result_summary is not None else getattr(log, "result", None),
        correlation_id=str(getattr(log, "id", None) or ""),
        execution_unit=unit,
    )

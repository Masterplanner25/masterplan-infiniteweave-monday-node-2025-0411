from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from AINDY.agents.agent_runtime.shared import get_runtime_compat_module


def _run_to_dict(run) -> dict:
    compat = get_runtime_compat_module()
    from AINDY.core.execution_record_service import record_from_agent_run

    capability_token = getattr(run, "capability_token", None)
    if not isinstance(capability_token, dict):
        capability_token = {}
    agent_type = getattr(run, "agent_type", None)
    if not isinstance(agent_type, str) or not agent_type:
        agent_type = "default"
    execution_token = getattr(run, "execution_token", None)
    if not isinstance(execution_token, str):
        execution_token = None
    return {
        "run_id": str(run.id),
        "user_id": run.user_id,
        "agent_type": agent_type,
        "objective": compat._run_objective(run),
        "executive_summary": run.executive_summary,
        "overall_risk": run.overall_risk,
        "status": run.status,
        "steps_total": run.steps_total,
        "steps_completed": run.steps_completed,
        "plan": run.plan,
        "result": run.result,
        "error_message": run.error_message,
        "flow_run_id": str(run.flow_run_id) if getattr(run, "flow_run_id", None) else None,
        "replayed_from_run_id": str(run.replayed_from_run_id) if getattr(run, "replayed_from_run_id", None) else None,
        "execution_token": execution_token,
        "granted_tools": capability_token.get("granted_tools", []),
        "allowed_capabilities": capability_token.get("allowed_capabilities", []),
        "correlation_id": getattr(run, "correlation_id", None),
        "trace_id": getattr(run, "trace_id", None),
        "parent_run_id": str(run.parent_run_id) if getattr(run, "parent_run_id", None) else None,
        "spawned_by_agent_id": str(run.spawned_by_agent_id) if getattr(run, "spawned_by_agent_id", None) else None,
        "coordination_role": getattr(run, "coordination_role", None),
        "execution_record": record_from_agent_run(run),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


run_to_dict = _run_to_dict


def _normalize_agent_events(timeline: Optional[dict]) -> list[dict]:
    if not timeline or not isinstance(timeline.get("events"), list):
        return []
    return [
        {
            "type": "agent.event",
            "event_type": event.get("event_type"),
            "timestamp": event.get("occurred_at"),
            "payload": event.get("payload", {}),
        }
        for event in timeline["events"]
    ]


def to_execution_response(run: dict, db: Session) -> dict:
    compat = get_runtime_compat_module()

    run_id = run.get("run_id")
    user_id = run.get("user_id")
    timeline = compat.get_run_events(run_id=run_id, user_id=user_id, db=db) if run_id and user_id else None
    result_payload = run.get("result")
    if result_payload is None:
        result_payload = {
            "objective": run.get("objective") or run.get(compat._OBJECTIVE_ATTR),
            "plan": run.get("plan"),
            "overall_risk": run.get("overall_risk"),
        }
    next_action = result_payload.get("next_action") if isinstance(result_payload, dict) else None
    return {
        "status": str(run.get("status", "unknown")).upper(),
        "result": result_payload,
        "events": _normalize_agent_events(timeline),
        "next_action": next_action,
        "trace_id": run.get("trace_id") or run.get("correlation_id") or run_id,
        "execution_record": run.get("execution_record"),
    }


def get_run_events(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    compat = get_runtime_compat_module()
    from AINDY.db.models.agent_event import AgentEvent
    from AINDY.db.models.agent_run import AgentRun, AgentStep

    try:
        db_run_id = compat._db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run or not compat._user_matches(run.user_id, user_id):
            return None

        lifecycle_events = [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "payload": row.payload or {},
            }
            for row in (
                db.query(AgentEvent)
                .filter(AgentEvent.run_id == run.id)
                .order_by(AgentEvent.occurred_at.asc())
                .all()
            )
        ]
        step_events = []
        for step in (
            db.query(AgentStep)
            .filter(AgentStep.run_id == run.id)
            .order_by(AgentStep.step_index.asc())
            .all()
        ):
            ts = step.executed_at or step.created_at
            step_events.append(
                {
                    "id": str(step.id),
                    "event_type": "STEP_EXECUTED" if step.status == "success" else "STEP_FAILED",
                    "occurred_at": ts.isoformat() if ts else None,
                    "payload": {
                        "step_index": step.step_index,
                        "tool_name": step.tool_name,
                        "risk_level": step.risk_level,
                        "description": step.description,
                        "status": step.status,
                        "execution_ms": step.execution_ms,
                        "error_message": step.error_message,
                    },
                }
            )
        all_events = lifecycle_events + step_events
        all_events.sort(key=lambda event: event["occurred_at"] or "0000")
        return {"run_id": str(run.id), "correlation_id": getattr(run, "correlation_id", None), "events": all_events}
    except Exception as exc:
        from AINDY.agents.agent_runtime.shared import logger

        logger.warning("[AgentRuntime] get_run_events failed for %s: %s", run_id, exc)
        return None

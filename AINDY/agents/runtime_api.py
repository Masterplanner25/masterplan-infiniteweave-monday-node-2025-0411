from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from AINDY.agents.agent_runtime import (
    approve_run,
    create_run,
    execute_run,
    get_run_events,
    reject_run,
    replay_run,
    run_to_dict,
    to_execution_response,
)
from AINDY.agents.agent_tools import TOOL_REGISTRY, suggest_tools
from AINDY.agents.autonomous_controller import (
    build_decision_response,
    evaluate_live_trigger,
    record_decision,
)
from AINDY.agents.capability_service import get_auto_grantable_tools
from AINDY.agents.stuck_run_service import recover_stuck_agent_run
from AINDY.core.execution_dispatcher import async_heavy_execution_enabled
from AINDY.db.models import AgentRun, AgentStep, AgentTrustSettings
from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
from AINDY.platform_layer.async_job_service import defer_async_job, submit_autonomous_async_job
from AINDY.platform_layer.trace_context import ensure_trace_id
from AINDY.utils.uuid_utils import normalize_uuid


def _normalize_run_id(run_id: str) -> Any:
    try:
        return normalize_uuid(run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid run_id") from exc


def _get_owned_run(*, db, user_id, run_id: str) -> AgentRun:
    normalized_run_id = _normalize_run_id(run_id)
    run = db.query(AgentRun).filter(AgentRun.id == normalized_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return run


def _decision_or_defer_response(
    *,
    db,
    user_id,
    trigger: dict[str, Any],
    trigger_context: dict[str, Any],
    task_name: str,
    payload: dict[str, Any],
):
    trace_id = ensure_trace_id()
    evaluation = evaluate_live_trigger(
        db=db,
        trigger=trigger,
        user_id=user_id,
        context=trigger_context,
    )
    record_decision(
        db=db,
        trigger=trigger,
        evaluation=evaluation,
        user_id=user_id,
        trace_id=trace_id,
        context=trigger_context,
    )

    if evaluation["decision"] == "ignore":
        return {"_decision_response": build_decision_response(evaluation, trace_id=trace_id)}

    if evaluation["decision"] == "defer":
        log_id = defer_async_job(
            task_name=task_name,
            payload=payload,
            user_id=user_id,
            source="agent_router",
            decision=evaluation,
        )
        return {
            "_http_status": 202,
            "_http_response": build_decision_response(
                evaluation,
                trace_id=log_id,
                result={
                    "automation_log_id": log_id,
                    "decision": "defer",
                    "reason": evaluation["reason"],
                },
                next_action={"type": "poll_automation_log", "automation_log_id": log_id},
            ),
        }

    return None


def create_agent_run_runtime(*, goal: str, db, user_id):
    goal = goal.strip()
    if async_heavy_execution_enabled():
        trigger_context = {"goal": goal, "importance": 0.95}
        return {
            "_http_status": 202,
            "_http_response": submit_autonomous_async_job(
                task_name="agent.create_run",
                payload={"goal": goal, "user_id": str(user_id)},
                user_id=user_id,
                source="agent_router",
                trigger_type="user",
                trigger_context=trigger_context,
                db=db,
            ),
        }

    decision = _decision_or_defer_response(
        db=db,
        user_id=user_id,
        trigger={"trigger_type": "user", "source": "agent_router", "goal": goal},
        trigger_context={"goal": goal, "importance": 0.95},
        task_name="agent.create_run",
        payload={
            "goal": goal,
            "user_id": str(user_id),
            "__autonomy": {
                "trigger_type": "user",
                "source": "agent_router",
                "context": {"goal": goal, "importance": 0.95},
            },
        },
    )
    if decision is not None:
        return decision

    run = create_run(goal=goal, user_id=user_id, db=db)
    if not run:
        raise HTTPException(status_code=500, detail="Failed to generate plan")
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
    return to_execution_response(run, db)


def list_agent_runs_runtime(*, db, user_id, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    query = db.query(AgentRun).filter(AgentRun.user_id == user_id)
    if status:
        query = query.filter(AgentRun.status == status)
    runs = query.order_by(AgentRun.created_at.desc()).limit(limit).all()
    rows = []
    for run in runs:
        row = run_to_dict(run)
        row["goal"] = row.get("objective")
        rows.append(row)
    return rows


def get_agent_run_runtime(*, db, user_id, run_id: str) -> dict[str, Any]:
    row = run_to_dict(_get_owned_run(db=db, user_id=user_id, run_id=run_id))
    row["goal"] = row.get("objective")
    return row


def approve_agent_run_runtime(*, db, user_id, run_id: str):
    trigger_context = {"goal": f"approve_run:{run_id}", "importance": 0.9}
    decision = _decision_or_defer_response(
        db=db,
        user_id=user_id,
        trigger={
            "trigger_type": "user",
            "source": "agent_router.approve",
            "goal": f"approve_run:{run_id}",
        },
        trigger_context=trigger_context,
        task_name="agent.approve_run",
        payload={
            "run_id": run_id,
            "user_id": str(user_id),
            "__autonomy": {
                "trigger_type": "user",
                "source": "agent_router.approve",
                "context": trigger_context,
            },
        },
    )
    if decision is not None:
        return decision

    run = approve_run(run_id=run_id, user_id=user_id, db=db)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not approvable")
    return to_execution_response(run, db)


def reject_agent_run_runtime(*, db, user_id, run_id: str):
    run = reject_run(run_id=run_id, user_id=user_id, db=db)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not rejectable")
    return to_execution_response(run, db)


def recover_agent_run_runtime(*, db, user_id, run_id: str, force: bool = False):
    result = recover_stuck_agent_run(run_id=run_id, user_id=user_id, db=db, force=force)
    if result["ok"]:
        return to_execution_response(result["run"], db)

    http_map = {"not_found": 404, "forbidden": 403, "wrong_status": 409, "too_recent": 409}
    raise HTTPException(
        status_code=http_map.get(result.get("error_code", "internal_error"), 500),
        detail=result.get("detail", result.get("error_code", "internal_error")),
    )


def replay_agent_run_runtime(*, db, user_id, run_id: str):
    new_run = replay_run(run_id=run_id, user_id=user_id, db=db)
    if not new_run:
        raise HTTPException(status_code=404, detail="Run not found or not replayable")
    return to_execution_response(new_run, db)


def list_agent_run_steps_runtime(*, db, user_id, run_id: str) -> list[dict[str, Any]]:
    run = _get_owned_run(db=db, user_id=user_id, run_id=run_id)
    steps = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id)
        .order_by(AgentStep.step_index.asc())
        .all()
    )
    return [
        {
            "step_index": step.step_index,
            "tool_name": step.tool_name,
            "description": step.description,
            "risk_level": step.risk_level,
            "status": step.status,
            "result": step.result,
            "error_message": step.error_message,
            "execution_ms": step.execution_ms,
            "executed_at": step.executed_at.isoformat() if step.executed_at else None,
        }
        for step in steps
    ]


def list_agent_run_events_runtime(*, db, user_id, run_id: str) -> dict[str, Any]:
    normalized_run_id = _normalize_run_id(run_id)
    result = get_run_events(run_id=run_id, user_id=user_id, db=db)
    if result is not None:
        return result

    run = db.query(AgentRun).filter(AgentRun.id == normalized_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    raise HTTPException(status_code=403, detail="Not authorized")


def list_agent_tools_runtime() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "risk": entry["risk"],
            "description": entry["description"],
            "capability": entry.get("capability"),
            "required_capability": entry.get("required_capability"),
            "category": entry.get("category"),
            "egress_scope": entry.get("egress_scope"),
        }
        for name, entry in TOOL_REGISTRY.items()
    ]


def get_agent_trust_runtime(*, db, user_id) -> dict[str, Any]:
    trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == user_id).first()
    return {
        "user_id": str(user_id),
        "auto_execute_low": trust.auto_execute_low if trust else False,
        "auto_execute_medium": trust.auto_execute_medium if trust else False,
        "allowed_auto_grant_tools": (
            trust.allowed_auto_grant_tools
            if trust and trust.allowed_auto_grant_tools is not None
            else get_auto_grantable_tools(user_id=user_id, db=db)
        ),
        "note": "High-risk plans always require approval regardless of trust settings.",
    }


def update_agent_trust_runtime(
    *,
    db,
    user_id,
    auto_execute_low: bool | None = None,
    auto_execute_medium: bool | None = None,
    allowed_auto_grant_tools: list[str] | None = None,
) -> dict[str, Any]:
    trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == user_id).first()
    if not trust:
        trust = AgentTrustSettings(user_id=user_id)
        db.add(trust)

    if auto_execute_low is not None:
        trust.auto_execute_low = auto_execute_low
    if auto_execute_medium is not None:
        trust.auto_execute_medium = auto_execute_medium
    if allowed_auto_grant_tools is not None:
        trust.allowed_auto_grant_tools = sorted(
            {
                tool_name
                for tool_name in allowed_auto_grant_tools
                if tool_name in TOOL_REGISTRY
                and TOOL_REGISTRY[tool_name]["risk"] in {"low", "medium"}
                and tool_name != "genesis.message"
            }
        )

    trust.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trust)
    return {
        "user_id": str(user_id),
        "auto_execute_low": trust.auto_execute_low,
        "auto_execute_medium": trust.auto_execute_medium,
        "allowed_auto_grant_tools": trust.allowed_auto_grant_tools or [],
        "note": "High-risk plans always require approval regardless of trust settings.",
    }


def get_agent_tool_suggestions_runtime(*, db, user_id) -> list[dict[str, Any]]:
    syscall_ctx = make_syscall_ctx_from_tool(
        str(user_id),
        capabilities=["analytics.read"],
    )
    syscall_ctx.metadata["_db"] = db
    result = get_dispatcher().dispatch(
        "sys.v1.analytics.get_kpi_snapshot",
        {"user_id": str(user_id)},
        syscall_ctx,
    )
    snapshot = result.get("data") if result.get("status") == "success" else None
    return suggest_tools(kpi_snapshot=snapshot, user_id=user_id, db=db)

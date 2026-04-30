from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from AINDY.agents.capability_service import mint_token
from AINDY.core.execution_signal_helper import record_agent_event
from AINDY.core.system_event_service import emit_error_event
from AINDY.platform_layer.trace_context import get_parent_event_id, get_trace_id

from AINDY.agents.agent_runtime.shared import get_runtime_compat_module, logger


def create_run(
    objective: str | None = None,
    user_id: str | None = None,
    db: Session | None = None,
    **values,
) -> Optional[dict]:
    try:
        compat = get_runtime_compat_module()
        from apps.agent.models.agent_run import AgentRun

        objective_text = compat._resolve_objective(objective, values)
        user_db_id = compat._db_user_id(user_id)
        plan = compat.generate_plan(objective=objective_text, user_id=user_db_id, db=db)
        if not plan:
            failure_reason = getattr(compat._plan_failure, "reason", "unknown failure")
            compat.emit_error_event(
                db=db,
                error_type="agent_plan_generation",
                message=f"Failed to generate agent plan: {failure_reason}",
                user_id=user_db_id,
                trace_id=get_trace_id(),
                parent_event_id=get_parent_event_id(),
                source="agent",
                payload={**compat._objective_preview(objective_text), "failure_reason": failure_reason},
                required=True,
            )
            return None

        overall_risk = plan.get("overall_risk", "high")
        needs_approval = compat._requires_approval(overall_risk, user_db_id, db)
        status = "pending_approval" if needs_approval else "approved"
        correlation_id = f"run_{uuid.uuid4()}"
        run = AgentRun(
            **{
                "user_id": user_db_id,
                "agent_type": "default",
                "trace_id": get_trace_id(),
                compat._OBJECTIVE_ATTR: objective_text,
                "plan": plan,
                "executive_summary": plan.get("executive_summary", ""),
                "overall_risk": overall_risk,
                "status": status,
                "steps_total": len(plan.get("steps", [])),
                "correlation_id": correlation_id,
            }
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService

            ExecutionUnitService(db).create(
                eu_type="agent",
                user_id=user_db_id,
                source_type="agent_run",
                source_id=str(run.id),
                correlation_id=correlation_id,
                status="pending",
                extra={**compat._objective_preview(objective_text), "overall_risk": overall_risk},
            )
        except Exception as eu_exc:
            logger.warning("[EU] agent hook create failed — non-fatal | error=%s", eu_exc)

        if status == "approved":
            token = mint_token(
                run_id=str(run.id),
                user_id=user_db_id,
                plan=plan,
                db=db,
                approval_mode="auto",
                agent_type=getattr(run, "agent_type", "default"),
            )
            if token:
                run.execution_token = token.get("execution_token")
                run.capability_token = token
                db.commit()
                db.refresh(run)
            else:
                logger.warning("[AgentRuntime] Auto-approval capability preflight failed for run %s", run.id)
                run.status = "pending_approval"
                run.error_message = "Capability preflight failed for auto-approval; manual approval required."
                db.commit()
                db.refresh(run)
                status = run.status

        logger.info("[AgentRuntime] Run created: %s (risk=%s, status=%s)", run.id, overall_risk, status)
        auto_executed = status == "approved"
        record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="PLAN_CREATED",
            db=db,
            correlation_id=correlation_id,
            payload={
                "overall_risk": overall_risk,
                "steps_total": len(plan.get("steps", [])),
                "auto_executed": auto_executed,
                **compat._objective_preview(objective_text),
                "requires_approval": not auto_executed,
            },
            required=True,
        )
        return compat._run_to_dict(run)
    except Exception as exc:
        compat = get_runtime_compat_module()

        logger.warning("[AgentRuntime] create_run failed: %s", exc)
        compat.emit_error_event(
            db=db,
            error_type="agent_create_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload=compat._objective_preview(compat._resolve_objective(objective, values)),
            required=True,
        )
        return None


def _create_run_from_plan(
    objective: str | None = None,
    plan: dict | None = None,
    user_id: str | None = None,
    db: Session | None = None,
    replayed_from_run_id: Optional[str] = None,
    **values,
) -> Optional[dict]:
    try:
        compat = get_runtime_compat_module()
        from apps.agent.models.agent_run import AgentRun

        objective_text = compat._resolve_objective(objective, values)
        plan = plan or {}
        overall_risk = plan.get("overall_risk", "high")
        needs_approval = compat._requires_approval(overall_risk, user_id, db)
        status = "pending_approval" if needs_approval else "approved"
        correlation_id = f"run_{uuid.uuid4()}"

        run = AgentRun(
            **{
                "user_id": user_id,
                "agent_type": "default",
                "trace_id": get_trace_id(),
                compat._OBJECTIVE_ATTR: objective_text,
                "plan": plan,
                "executive_summary": plan.get("executive_summary", ""),
                "overall_risk": overall_risk,
                "status": status,
                "steps_total": len(plan.get("steps", [])),
                "replayed_from_run_id": replayed_from_run_id,
                "correlation_id": correlation_id,
            }
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        if status == "approved":
            token = mint_token(
                run_id=str(run.id),
                user_id=user_id,
                plan=plan,
                db=db,
                approval_mode="auto",
                agent_type=getattr(run, "agent_type", "default"),
            )
            if token:
                run.execution_token = token.get("execution_token")
                run.capability_token = token
                db.commit()
                db.refresh(run)
            else:
                run.status = "pending_approval"
                run.error_message = "Capability preflight failed for auto-approval; manual approval required."
                db.commit()
                db.refresh(run)

        logger.info(
            "[AgentRuntime] Replay run created: %s (origin=%s, risk=%s, status=%s)",
            run.id,
            replayed_from_run_id,
            overall_risk,
            status,
        )
        return compat._run_to_dict(run)
    except Exception as exc:
        logger.warning("[AgentRuntime] _create_run_from_plan failed: %s", exc)
        return None

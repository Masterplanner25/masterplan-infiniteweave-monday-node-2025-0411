from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from AINDY.agents.capability_service import mint_token
from AINDY.core.execution_signal_helper import record_agent_event
from AINDY.core.system_event_service import emit_error_event
from AINDY.platform_layer.trace_context import get_parent_event_id, get_trace_id

from AINDY.agents.agent_runtime.shared import get_runtime_compat_module, logger


def approve_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    try:
        compat = get_runtime_compat_module()
        from AINDY.db.models.agent_run import AgentRun

        user_db_id = compat._db_user_id(user_id)
        db_run_id = compat._db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run or not compat._user_matches(run.user_id, user_db_id):
            return None
        if run.status != "pending_approval":
            return compat._run_to_dict(run)

        run.status = "approved"
        run.approved_at = datetime.now(timezone.utc)
        token = mint_token(
            run_id=str(run.id),
            user_id=user_db_id,
            plan=run.plan,
            db=db,
            approval_mode="manual",
            agent_type=getattr(run, "agent_type", "default"),
        )
        if not token:
            db.rollback()
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.error_message = "Capability preflight failed; run not approved."
                db.commit()
                db.refresh(run)
                return compat._run_to_dict(run)
            return None

        run.execution_token = token.get("execution_token")
        run.capability_token = token
        run.error_message = None
        db.commit()
        record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="APPROVED",
            db=db,
            correlation_id=getattr(run, "correlation_id", None),
            payload={"auto_executed": False},
            required=True,
        )
        return compat.execute_run(run_id=run.id, user_id=user_db_id, db=db)
    except Exception as exc:
        compat = get_runtime_compat_module()
        logger.warning("[AgentRuntime] approve_run failed for %s: %s", run_id, exc)
        compat.emit_error_event(
            db=db,
            error_type="agent_approve_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"run_id": str(run_id)},
            required=True,
        )
        return None


def reject_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    try:
        compat = get_runtime_compat_module()
        from AINDY.db.models.agent_run import AgentRun

        user_db_id = compat._db_user_id(user_id)
        db_run_id = compat._db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run or not compat._user_matches(run.user_id, user_db_id):
            return None
        if run.status != "pending_approval":
            return compat._run_to_dict(run)

        run.status = "rejected"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="REJECTED",
            db=db,
            correlation_id=getattr(run, "correlation_id", None),
            payload={},
            required=True,
        )
        return compat._run_to_dict(run)
    except Exception as exc:
        compat = get_runtime_compat_module()
        logger.warning("[AgentRuntime] reject_run failed for %s: %s", run_id, exc)
        compat.emit_error_event(
            db=db,
            error_type="agent_reject_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"run_id": str(run_id)},
            required=True,
        )
        return None

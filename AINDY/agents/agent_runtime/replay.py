from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from AINDY.core.execution_signal_helper import record_agent_event
from AINDY.core.system_event_service import emit_error_event
from AINDY.platform_layer.trace_context import get_parent_event_id, get_trace_id

from AINDY.agents.agent_runtime.shared import get_runtime_compat_module, logger


def replay_run(run_id: str, user_id: str, db: Session, mode: str = "same_plan") -> Optional[dict]:
    try:
        compat = get_runtime_compat_module()
        from AINDY.db.models.agent_run import AgentRun

        db_run_id = compat._db_run_id(run_id)
        original = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not original:
            logger.warning("[AgentRuntime] replay_run: run %s not found", run_id)
            return None
        if not compat._user_matches(original.user_id, user_id):
            logger.warning("[AgentRuntime] replay_run: owner mismatch for %s", run_id)
            return None

        if mode == "new_plan":
            original_objective = compat._run_objective(original)
            plan = compat.generate_plan(objective=original_objective, user_id=user_id, db=db)
            if not plan:
                logger.warning("[AgentRuntime] replay_run new_plan: plan generation failed for %s", run_id)
                return None
        else:
            original_objective = compat._run_objective(original)
            plan = original.plan or {}

        new_run = compat._create_run_from_plan(
            original_objective,
            plan=plan,
            user_id=user_id,
            db=db,
            replayed_from_run_id=str(original.id),
        )
        if not new_run:
            return None

        record_agent_event(
            run_id=new_run["run_id"],
            user_id=user_id,
            event_type="REPLAY_CREATED",
            db=db,
            correlation_id=new_run.get("correlation_id"),
            payload={"original_run_id": str(original.id), "mode": mode},
            required=True,
        )
        return new_run
    except Exception as exc:
        compat = get_runtime_compat_module()
        logger.warning("[AgentRuntime] replay_run failed for %s: %s", run_id, exc)
        compat.emit_error_event(
            db=db,
            error_type="agent_replay_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"run_id": str(run_id), "mode": mode},
            required=True,
        )
        return None

"""
NodusAgentAdapter — Sprint N+6 Deterministic Agent

Replaces the N+4 sequential executor for-loop with a PersistentFlowRunner
backed workflow, giving the agent per-step retry semantics, DB checkpointing
after every step, and FlowHistory → Memory Bridge capture on completion.

Architecture
============
execute_with_flow()
  └─ PersistentFlowRunner(AGENT_FLOW, ...)
       ├─ agent_validate_steps   validate plan, initialise iteration state
       ├─ agent_execute_step     execute one step, loop back until all done
       └─ agent_finalize_run     mark AgentRun completed, write step results

Retry policy (per step, enforced inside agent_execute_step)
===========================================================
  low / medium risk  → retry up to MAX_STEP_RETRIES (3) times, then FAILURE
  high risk          → FAILURE immediately on first tool error (no retry)

High-risk no-retry rule prevents tools like genesis.message from being
silently replayed if they partially succeed.

Note on nodus pip package
=========================
The installed ``nodus`` package is a separate scripting-language VM
(checkpoints to filesystem JSON, requires Nodus VM closures).  It has no
integration path with AINDY's PostgreSQL stack and is NOT imported here.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.execution_signal_helper import queue_system_event, record_agent_event
from services.capability_service import check_execution_capability, check_tool_capability
from services.agent_tools import execute_tool
from services.flow_engine import PersistentFlowRunner, register_node
from services.system_event_service import emit_error_event
from services.system_event_types import SystemEventTypes
from utils.user_ids import parse_user_id

logger = logging.getLogger(__name__)
from services.observability_events import emit_observability_event

MAX_STEP_RETRIES = 3


def _db_run_id(run_id):
    parsed = parse_user_id(run_id)
    return parsed if parsed is not None else run_id


# ── Node: agent_validate_steps ────────────────────────────────────────────────

@register_node("agent_validate_steps")
def agent_validate_steps(state: dict, context: dict) -> dict:
    """
    Validate the plan contains at least one step and initialise iteration
    state for the executor loop.

    Returns FAILURE when plan is empty so the flow halts immediately rather
    than reaching agent_finalize_run with nothing to record.
    """
    steps = state.get("steps", [])
    if not steps:
        return {
            "status": "FAILURE",
            "error": "Plan has no steps to execute",
            "output_patch": {},
        }
    logger.info(
        "[NodusAdapter] Validating %d-step plan for AgentRun %s",
        len(steps),
        state.get("agent_run_id"),
    )
    return {
        "status": "SUCCESS",
        "output_patch": {
            "current_step_index": 0,
            "step_results": [],
        },
    }


# ── Node: agent_execute_step ──────────────────────────────────────────────────

@register_node("agent_execute_step")
def agent_execute_step(state: dict, context: dict) -> dict:
    """
    Execute the step at state["current_step_index"].

    Retry policy
    ------------
    - high risk   : 1 attempt; return FAILURE immediately on tool error
    - low / medium: up to MAX_STEP_RETRIES attempts; return FAILURE only when
                    all attempts are exhausted

    Persistence
    -----------
    Writes one AgentStep audit row per execution and increments
    AgentRun.steps_completed / current_step on every call (success or fail).

    The PersistentFlowRunner will loop back to this node via the conditional
    edge _more_steps() while current_step_index < len(steps), then advance
    to agent_finalize_run when all steps are done.
    """
    from db.models.agent_run import AgentRun, AgentStep

    steps = state.get("steps", [])
    idx = state.get("current_step_index", 0)

    # Guard: should not be reached because the conditional edge prevents it
    if idx >= len(steps):
        return {"status": "SUCCESS", "output_patch": {}}

    step = steps[idx]
    tool_name = step.get("tool", "")
    tool_args = step.get("args", {})
    risk_level = step.get("risk_level", "high")
    description = step.get("description", "")
    agent_run_id = state["agent_run_id"]
    agent_run_db_id = _db_run_id(agent_run_id)
    user_id = state["user_id"]
    execution_token = state.get("execution_token") or state.get("capability_token")
    db: Session = context["db"]

    capability_check = {"ok": True, "error": None, "granted_tools": []}
    if "execution_token" in state or "capability_token" in state:
        capability_check = check_tool_capability(
            token=execution_token,
            run_id=agent_run_id,
            user_id=user_id,
            tool_name=tool_name,
        )
    if not capability_check["ok"]:
        error_msg = (
            f"Capability denied for step {idx} ({tool_name}): "
            f"{capability_check['error']}"
        )

        agent_step = AgentStep(
            run_id=agent_run_db_id,
            step_index=idx,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=risk_level,
            description=description,
            status="failed",
            result=None,
            error_message=error_msg,
            execution_ms=0,
            executed_at=datetime.now(timezone.utc),
            correlation_id=state.get("correlation_id"),
        )
        db.add(agent_step)

        agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_db_id).first()
        if agent_run:
            agent_run.steps_completed = idx + 1
            agent_run.current_step = idx + 1
        db.commit()

        from services.agent_event_service import emit_event
        record_agent_event(
            run_id=agent_run_id,
            user_id=user_id,
            event_type="CAPABILITY_DENIED",
            db=db,
            correlation_id=state.get("correlation_id"),
            payload={
                "step_index": idx,
                "tool_name": tool_name,
                "error": capability_check["error"],
                "granted_tools": capability_check.get("granted_tools", []),
            },
            required=True,
        )
        queue_system_event(
            db=db,
            event_type=SystemEventTypes.AGENT_STEP,
            user_id=user_id,
            trace_id=state.get("correlation_id") or context.get("trace_id"),
            source="agent",
            payload={
                "run_id": str(agent_run_id),
                "step_index": idx,
                "tool_name": tool_name,
                "status": "failed",
                "error": error_msg,
            },
            required=True,
        )

        step_result_dict = {
            "step_index": idx,
            "tool": tool_name,
            "status": "failed",
            "result": None,
            "error": error_msg,
        }
        new_step_results = list(state.get("step_results", [])) + [step_result_dict]
        logger.warning("[NodusAdapter] %s", error_msg)
        return {
            "status": "FAILURE",
            "error": error_msg,
            "output_patch": {"step_results": new_step_results},
        }

    # Execute with per-step retry
    max_attempts = 1 if risk_level == "high" else MAX_STEP_RETRIES
    tool_result = None
    exec_ms = 0

    for attempt in range(1, max_attempts + 1):
        start_ms = int(time.time() * 1000)
        tool_result = execute_tool(
            tool_name=tool_name,
            args=tool_args,
            user_id=user_id,
            db=db,
            run_id=agent_run_id,
            execution_token=execution_token,
        )
        exec_ms = int(time.time() * 1000) - start_ms

        if tool_result["success"]:
            break

        if risk_level == "high":
            break  # High-risk: no retry regardless

        if attempt < max_attempts:
            logger.warning(
                "[NodusAdapter] Step %d (%s, risk=%s) attempt %d/%d failed: %s",
                idx, tool_name, risk_level, attempt, max_attempts,
                tool_result.get("error"),
            )

    step_status = "success" if tool_result["success"] else "failed"

    # Persist AgentStep audit record
    agent_step = AgentStep(
        run_id=agent_run_db_id,
        step_index=idx,
        tool_name=tool_name,
        tool_args=tool_args,
        risk_level=risk_level,
        description=description,
        status=step_status,
        result=tool_result.get("result"),
        error_message=tool_result.get("error"),
        execution_ms=exec_ms,
        executed_at=datetime.now(timezone.utc),
        correlation_id=state.get("correlation_id"),
    )
    db.add(agent_step)

    # Update AgentRun progress counters
    agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_db_id).first()
    if agent_run:
        agent_run.steps_completed = idx + 1
        agent_run.current_step = idx + 1
    db.commit()
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.AGENT_STEP,
        user_id=user_id,
        trace_id=state.get("correlation_id") or context.get("trace_id"),
        source="agent",
        payload={
            "run_id": str(agent_run_id),
            "step_index": idx,
            "tool_name": tool_name,
            "status": step_status,
            "error": tool_result.get("error"),
        },
        required=True,
    )

    step_result_dict = {
        "step_index": idx,
        "tool": tool_name,
        "status": step_status,
        "result": tool_result.get("result"),
        "error": tool_result.get("error"),
    }
    new_step_results = list(state.get("step_results", [])) + [step_result_dict]

    if not tool_result["success"]:
        retry_note = (
            "" if risk_level == "high"
            else f" after {max_attempts} attempt(s)"
        )
        error_msg = (
            f"Step {idx} ({tool_name}, {risk_level})"
            f" failed{retry_note}: {tool_result.get('error')}"
        )
        logger.warning("[NodusAdapter] %s", error_msg)
        return {
            "status": "FAILURE",
            "error": error_msg,
            "output_patch": {"step_results": new_step_results},
        }

    logger.info("[NodusAdapter] Step %d (%s) succeeded in %dms", idx, tool_name, exec_ms)
    return {
        "status": "SUCCESS",
        "output_patch": {
            "current_step_index": idx + 1,
            "step_results": new_step_results,
        },
    }


# ── Node: agent_finalize_run ──────────────────────────────────────────────────

@register_node("agent_finalize_run")
def agent_finalize_run(state: dict, context: dict) -> dict:
    """
    Finalise a successful agent run.

    Marks AgentRun.status = "completed" and writes the accumulated
    step_results to AgentRun.result.

    After this node returns SUCCESS, PersistentFlowRunner calls
    _capture_flow_completion() which writes the execution summary to the
    Memory Bridge via MemoryCaptureEngine.
    """
    from db.models.agent_run import AgentRun

    agent_run_id = state["agent_run_id"]
    agent_run_db_id = _db_run_id(agent_run_id)
    step_results = state.get("step_results", [])
    db: Session = context["db"]

    agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_db_id).first()

    result_payload = {"steps": step_results}
    if agent_run and state.get("user_id"):
        from services.infinity_orchestrator import execute as execute_infinity_orchestrator

        orchestration = execute_infinity_orchestrator(
            user_id=state["user_id"],
            trigger_event="agent_completed",
            db=db,
        )
        result_payload = {
            "steps": step_results,
            "loop_enforced": True,
            "next_action": orchestration["next_action"],
        }

    if agent_run:
        agent_run.status = "completed"
        agent_run.completed_at = datetime.now(timezone.utc)
        agent_run.result = result_payload
        db.commit()
        logger.info(
            "[NodusAdapter] AgentRun %s finalised as completed (%d steps)",
            agent_run_id,
            len(step_results),
        )

    # Emit COMPLETED lifecycle event
    from services.agent_event_service import emit_event
    record_agent_event(
        run_id=agent_run_id,
        user_id=state.get("user_id", ""),
        event_type="COMPLETED",
        db=db,
        correlation_id=state.get("correlation_id"),
        payload={"steps_completed": len(step_results), "loop_enforced": bool(result_payload.get("loop_enforced"))},
        required=True,
    )

    return {
        "status": "SUCCESS",
        "output_patch": {"finalized": True},
    }


# ── Flow graph ────────────────────────────────────────────────────────────────

def _more_steps(state: dict) -> bool:
    """Return True while there are unexecuted steps remaining."""
    return state.get("current_step_index", 0) < len(state.get("steps", []))


AGENT_FLOW = {
    "start": "agent_validate_steps",
    "edges": {
        "agent_validate_steps": ["agent_execute_step"],
        "agent_execute_step": [
            # Loop back to execute next step while steps remain
            {"condition": _more_steps, "target": "agent_execute_step"},
            # All steps done — advance to finalizer
            {"condition": lambda s: True, "target": "agent_finalize_run"},
        ],
        "agent_finalize_run": [],
    },
    "end": ["agent_finalize_run"],
}


# ── Adapter entry point ───────────────────────────────────────────────────────

class NodusAgentAdapter:
    """
    Deterministic execution adapter for agent plans (Sprint N+6).

    Delegates plan execution to PersistentFlowRunner via AGENT_FLOW,
    replacing the N+4 sequential for-loop in services/agent_runtime.py.
    """

    @staticmethod
    def execute_with_flow(
        run_id: str,
        plan: dict,
        user_id: str,
        db: Session,
        correlation_id: Optional[str] = None,
        execution_token: Optional[dict] = None,
        capability_token: Optional[dict] = None,
    ) -> dict:
        """
        Execute an agent plan as a PersistentFlowRunner workflow.

        Steps:
          1. Build initial state from plan steps.
          2. Start PersistentFlowRunner — runs validate → execute(loop) → finalize.
          3. Link FlowRun.id → AgentRun.flow_run_id for audit trail.
          4. On FAILURE: finalise the AgentRun (mark failed, write step results).

        Returns the flow result dict:
          {"status": "SUCCESS" | "FAILED", "run_id": <flow_run_id>, ...}

        Never raises — all exceptions are caught and treated as failures.
        """
        from db.models.agent_run import AgentRun, AgentStep

        try:
            steps = (plan or {}).get("steps", [])
            scoped_token = execution_token or capability_token
            flow_capability_check = {"ok": False, "error": "missing scoped capability token"}
            if scoped_token is not None:
                flow_capability_check = check_execution_capability(
                    token=scoped_token,
                    run_id=run_id,
                    user_id=user_id,
                    capability_name="execute_flow",
                )
            if not flow_capability_check["ok"]:
                from db.models.agent_run import AgentRun
                from services.agent_event_service import emit_event

                agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
                if agent_run and agent_run.status == "executing":
                    agent_run.status = "failed"
                    agent_run.completed_at = datetime.now(timezone.utc)
                    agent_run.error_message = flow_capability_check["error"]
                    agent_run.result = {"steps": []}
                queue_system_event(
                    db=db,
                    event_type="capability.denied",
                    user_id=user_id,
                    trace_id=correlation_id,
                    source="agent",
                    payload={
                        "run_id": str(run_id),
                        "capability": "execute_flow",
                        "error": flow_capability_check["error"],
                    },
                    required=True,
                )
                record_agent_event(
                    run_id=run_id,
                    user_id=user_id,
                    event_type="CAPABILITY_DENIED",
                    db=db,
                    correlation_id=correlation_id,
                    payload={
                        "capability": "execute_flow",
                        "error": flow_capability_check["error"],
                    },
                    required=True,
                )
                logger.warning(
                    "[NodusAdapter] Flow capability denied for AgentRun %s: %s",
                    run_id,
                    flow_capability_check["error"],
                )
                return {
                    "status": "FAILED",
                    "error": flow_capability_check["error"],
                }
            queue_system_event(
                db=db,
                event_type="capability.allowed",
                user_id=user_id,
                trace_id=correlation_id,
                source="agent",
                payload={
                    "run_id": str(run_id),
                    "capability": "execute_flow",
                },
                required=True,
            )

            initial_state = {
                "agent_run_id": run_id,
                "user_id": user_id,
                "steps": steps,
                "memory_context": (plan or {}).get("memory_context", {}),
                "current_step_index": 0,
                "step_results": [],
                "correlation_id": correlation_id,
                "execution_token": scoped_token,
            }

            runner = PersistentFlowRunner(
                flow=AGENT_FLOW,
                db=db,
                user_id=user_id,
                workflow_type="agent_execution",
            )

            logger.info(
                "[NodusAdapter] Starting flow for AgentRun %s (%d steps)",
                run_id,
                len(steps),
            )
            flow_result = runner.start(initial_state, flow_name="agent_execution")

            # Link FlowRun ID back to AgentRun for audit trail
            flow_run_id = flow_result.get("run_id")
            if flow_run_id:
                agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
                if agent_run:
                    agent_run.flow_run_id = str(flow_run_id)
                    db.commit()

            # On FAILURE: agent_finalize_run never ran — finalise AgentRun here
            if flow_result.get("status") != "SUCCESS":
                agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
                if agent_run and agent_run.status == "executing":
                    # Load all AgentStep rows written before the failure
                    completed_steps = (
                        db.query(AgentStep)
                        .filter(AgentStep.run_id == _db_run_id(run_id))
                        .order_by(AgentStep.step_index.asc())
                        .all()
                    )
                    step_results = [
                        {
                            "step_index": s.step_index,
                            "tool": s.tool_name,
                            "status": s.status,
                            "result": s.result,
                            "error": s.error_message,
                        }
                        for s in completed_steps
                    ]
                    agent_run.status = "failed"
                    agent_run.completed_at = datetime.now(timezone.utc)
                    agent_run.result = {"steps": step_results}
                    agent_run.error_message = flow_result.get(
                        "error", "Flow execution failed"
                    )
                    db.commit()
                    logger.warning(
                        "[NodusAdapter] AgentRun %s finalised as failed: %s",
                        run_id,
                        agent_run.error_message,
                    )
                    # Emit EXECUTION_FAILED lifecycle event
                    from services.agent_event_service import emit_event
                    record_agent_event(
                        run_id=run_id,
                        user_id=user_id,
                        event_type="EXECUTION_FAILED",
                        db=db,
                        correlation_id=correlation_id,
                        payload={"error": agent_run.error_message},
                        required=True,
                    )

            return flow_result

        except Exception as exc:
            logger.error(
                "[NodusAdapter] execute_with_flow raised for AgentRun %s: %s",
                run_id,
                exc,
            )
            # Best-effort failure finalisation
            try:
                agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
                if agent_run and agent_run.status == "executing":
                    agent_run.status = "failed"
                    agent_run.completed_at = datetime.now(timezone.utc)
                    agent_run.error_message = f"Adapter error: {exc}"
                    db.commit()
                    from services.agent_event_service import emit_event
                    record_agent_event(
                        run_id=run_id,
                        user_id=user_id,
                        event_type="EXECUTION_FAILED",
                        db=db,
                        correlation_id=correlation_id,
                        payload={"error": f"Adapter error: {exc}"},
                        required=True,
                    )
            except Exception:
                try:
                    emit_error_event(
                        db=db,
                        error_type="agent_adapter",
                        message=str(exc),
                        user_id=user_id,
                        trace_id=correlation_id,
                        source="agent",
                        payload={"run_id": run_id},
                        required=True,
                    )
                except Exception:
                    logger.exception("[NodusAdapter] required adapter error event failed for %s", run_id)
                emit_observability_event(
                    logger,
                    event="nodus_adapter_failure_finalization_failed",
                    run_id=run_id,
                    error=str(exc),
                )
            return {"status": "FAILED", "error": str(exc)}


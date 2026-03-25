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

from sqlalchemy.orm import Session

from services.agent_tools import execute_tool
from services.flow_engine import PersistentFlowRunner, register_node

logger = logging.getLogger(__name__)

MAX_STEP_RETRIES = 3


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
    user_id = state["user_id"]
    db: Session = context["db"]

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
        run_id=agent_run_id,
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
    )
    db.add(agent_step)

    # Update AgentRun progress counters
    agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
    if agent_run:
        agent_run.steps_completed = idx + 1
        agent_run.current_step = idx + 1
    db.commit()

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
    step_results = state.get("step_results", [])
    db: Session = context["db"]

    agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
    if agent_run:
        agent_run.status = "completed"
        agent_run.completed_at = datetime.now(timezone.utc)
        agent_run.result = {"steps": step_results}
        db.commit()
        logger.info(
            "[NodusAdapter] AgentRun %s finalised as completed (%d steps)",
            agent_run_id,
            len(step_results),
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
            initial_state = {
                "agent_run_id": run_id,
                "user_id": user_id,
                "steps": steps,
                "current_step_index": 0,
                "step_results": [],
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
                agent_run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
                if agent_run:
                    agent_run.flow_run_id = str(flow_run_id)
                    db.commit()

            # On FAILURE: agent_finalize_run never ran — finalise AgentRun here
            if flow_result.get("status") != "SUCCESS":
                agent_run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
                if agent_run and agent_run.status == "executing":
                    # Load all AgentStep rows written before the failure
                    completed_steps = (
                        db.query(AgentStep)
                        .filter(AgentStep.run_id == run_id)
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

            return flow_result

        except Exception as exc:
            logger.error(
                "[NodusAdapter] execute_with_flow raised for AgentRun %s: %s",
                run_id,
                exc,
            )
            # Best-effort failure finalisation
            try:
                agent_run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
                if agent_run and agent_run.status == "executing":
                    agent_run.status = "failed"
                    agent_run.completed_at = datetime.now(timezone.utc)
                    agent_run.error_message = f"Adapter error: {exc}"
                    db.commit()
            except Exception:
                pass
            return {"status": "FAILED", "error": str(exc)}

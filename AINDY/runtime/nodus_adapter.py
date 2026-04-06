"""
NodusAgentAdapter — Sprint N+6 Deterministic Agent
+ nodus.execute / nodus_record_outcome / nodus_handle_error flow nodes

Sprint N+6
==========
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

nodus.execute node (bottom of this file)
========================================
Registers the "nodus.execute" flow node so any flow graph can execute a Nodus
script or file as a first-class node.  See NodusRuntimeAdapter in
nodus_runtime_adapter.py for the full execution contract.

  State inputs:  nodus_script | nodus_file_path, nodus_input_payload,
                 nodus_error_policy ("fail" | "retry")
  State outputs: nodus_status, nodus_output_state, nodus_events,
                 nodus_memory_writes, nodus_execute_result

Also registers helper end-nodes for NODUS_SCRIPT_FLOW:
  nodus_record_outcome  — log results on success path
  nodus_handle_error    — surface error on failure path
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.execution_signal_helper import queue_system_event, record_agent_event
emit_system_event = queue_system_event
from agents.capability_service import check_execution_capability, check_tool_capability
from agents.agent_tools import execute_tool
from runtime.flow_engine import PersistentFlowRunner, register_node
from runtime.nodus_execution_service import build_nodus_execution_summary
from runtime.nodus_execution_service import execute_nodus_runtime
from core.system_event_service import emit_error_event
from core.system_event_types import SystemEventTypes
from utils.user_ids import parse_user_id

logger = logging.getLogger(__name__)
from core.observability_events import emit_observability_event

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

        from agents.agent_event_service import emit_event
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
        emit_system_event(
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
        emit_system_event(
            db=db,
            event_type=SystemEventTypes.AGENT_STEP_FAILED,
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

    # ── Memory Injection (tool execution) ─────────────────────────────────────
    # Enrich context with memories recalled for this specific tool so the tool
    # implementation (and any node that reads context["memory_context"]) can
    # adapt its behaviour based on past outcomes.
    context["tool_name"] = tool_name
    from memory.memory_helpers import enrich_context
    enrich_context(context)
    # ──────────────────────────────────────────────────────────────────────────

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
    emit_system_event(
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
    emit_system_event(
        db=db,
        event_type=(
            SystemEventTypes.AGENT_STEP_COMPLETED
            if step_status == "success"
            else SystemEventTypes.AGENT_STEP_FAILED
        ),
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
        from domain.infinity_orchestrator import execute as execute_infinity_orchestrator

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
    from agents.agent_event_service import emit_event
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
        from runtime.nodus_execution_service import execute_agent_flow_orchestration

        return execute_agent_flow_orchestration(
            run_id=run_id,
            plan=plan,
            user_id=user_id,
            db=db,
            correlation_id=correlation_id,
            execution_token=execution_token,
            capability_token=capability_token,
        )


NodusAgentAdapter.execute_with_flow.__aindy_compat_wrapper__ = True


# ── nodus.execute node ────────────────────────────────────────────────────────
#
# Registered here because this module already carries the full flow_engine
# import chain.  The execution contract (NodusExecutionContext, NodusExecutionResult,
# NodusRuntimeAdapter) lives in nodus_runtime_adapter.py.
#
# Node name: "nodus.execute"
# Flow definition: NODUS_SCRIPT_FLOW  (importable from nodus_runtime_adapter)

@register_node("nodus.execute")
def nodus_execute_node(state: dict, context: dict) -> dict:
    """
    Execute a Nodus script or file as a flow node.

    State inputs
    ------------
    nodus_script        str  — inline Nodus source code (takes priority over file)
    nodus_file_path     str  — path to a .nodus file
    nodus_input_payload dict — extra inputs exposed as the ``input_payload`` global
                               inside the script (optional)
    nodus_error_policy  str  — "fail" (default) | "retry"
                               fail  → VM error returns FAILURE immediately
                               retry → VM error returns RETRY (honours POLICY max_retries)
    execution_unit_id   str  — optional override; defaults to the flow run_id

    State outputs  (merged into flow state on SUCCESS / FAILURE / WAIT)
    -------------------------------------------------------------------
    nodus_status          "success" | "failure" | "waiting"
    nodus_output_state    dict — mutations made by set_state() inside the script
    nodus_events          list — events emitted by emit() / event.emit()
    nodus_memory_writes   list — memory nodes written by remember() / memory.write()
    nodus_execute_result  dict — {status, output_state, events_emitted,
                                  memory_writes, error}
    nodus_error           str  — set only on failure
    nodus_wait_event_type str  — set only on WAIT; cleared on resume
    nodus_received_events dict — {event_type: payload} for events delivered
                                 after an event.wait() (populated on resume)

    Flow engine integration
    -----------------------
    * memory_context is pre-populated by execute_node() via enrich_context()
      BEFORE this function runs; it is passed through to the VM as-is.
    * Nodus emit() calls are queued as SystemEvents (source="nodus") using the
      flow's trace_id so they appear in the same RippleTrace chain.
    * Nodus remember() calls are flushed as memory captures after the script
      exits (non-fatal — a single bad write does not abort the node).
    * RETRY status lets the flow engine's attempt counter and max_retries gate
      apply exactly as they do for any other node that returns RETRY.
    """
    from runtime.nodus_runtime_adapter import _build_event_sink, _flush_memory_writes
    from core.execution_signal_helper import queue_system_event
    from core.system_event_types import SystemEventTypes

    db = context["db"]
    user_id: str = str(context.get("user_id") or "")
    run_id: str = str(context.get("run_id") or "")
    trace_id: str = str(context.get("trace_id") or run_id)
    flow_name: str = str(context.get("flow_name") or context.get("workflow_type") or "")

    # ── Resume bridge ─────────────────────────────────────────────────────────
    # When route_event() resumes a waiting flow run it injects state["event"]
    # with the received event payload and clears waiting_for.  Bridge that
    # into nodus_received_events so event.wait() returns the payload on the
    # re-execution without raising NodusWaitSignal again.
    incoming_event = state.pop("event", None)
    pending_wait_type: Optional[str] = state.get("nodus_wait_event_type")
    if incoming_event is not None and pending_wait_type:
        received = dict(state.get("nodus_received_events") or {})
        received[pending_wait_type] = (
            incoming_event if isinstance(incoming_event, dict) else {"payload": incoming_event}
        )
        state["nodus_received_events"] = received
        state.pop("nodus_wait_event_type", None)
        emit_system_event(
            db=db,
            event_type=SystemEventTypes.NODUS_EVENT_WAIT_RESUMED,
            user_id=user_id,
            trace_id=trace_id,
            source="nodus",
            payload={
                "run_id": run_id,
                "waited_for": pending_wait_type,
                "event_payload": incoming_event if isinstance(incoming_event, dict) else {},
            },
            required=False,
        )
        logger.info(
            "[nodus.execute] Resuming on '%s' eu=%s", pending_wait_type, run_id
        )

    # ── Resolve script source ─────────────────────────────────────────────────
    script: Optional[str] = state.get("nodus_script")
    file_path: Optional[str] = state.get("nodus_file_path")

    if not script and not file_path:
        return {
            "status": "FAILURE",
            "error": (
                "nodus.execute requires state['nodus_script'] "
                "or state['nodus_file_path']"
            ),
            "output_patch": {},
        }

    # ── Derive execution_unit_id ──────────────────────────────────────────────
    execution_unit_id: str = str(state.get("execution_unit_id") or run_id)

    # ── Build NodusExecutionContext ───────────────────────────────────────────
    # memory_context is already enriched by execute_node() → enrich_context().
    # Pass it through unchanged so the script sees the same memory nodes.
    # Seed the script's internal state with nodus_received_events from the flow
    # state so event.wait() returns the payload on the resume path.
    # All other flow state keys are kept out of the script's namespace.
    nodus_initial_state: dict = {}
    if state.get("nodus_received_events"):
        nodus_initial_state["nodus_received_events"] = dict(state["nodus_received_events"])

    # ── Emit nodus.execute.started ────────────────────────────────────────────
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.NODUS_EXECUTE_STARTED,
        user_id=user_id,
        trace_id=trace_id,
        source="nodus",
        payload={
            "run_id": run_id,
            "execution_unit_id": execution_unit_id,
            "flow_name": flow_name,
            "source": "script" if script else "file",
            "file_path": file_path,
        },
        required=False,
    )

    # ── Execute via NodusRuntimeAdapter ──────────────────────────────────────
    nodus_result = execute_nodus_runtime(
        db=db,
        user_id=user_id,
        execution_unit_id=execution_unit_id,
        script=script,
        file_path=file_path,
        memory_context=context.get("memory_context") or {},
        input_payload=state.get("nodus_input_payload") or {},
        state=nodus_initial_state,
        event_sink=_build_event_sink(
            db=db,
            user_id=user_id,
            trace_id=trace_id,
            execution_unit_id=execution_unit_id,
        ),
    )

    # ── WAIT path ─────────────────────────────────────────────────────────────
    if nodus_result.status == "waiting":
        raw = nodus_result.raw_result or {}
        wait_for = raw.get("wait_for") or state.get("nodus_wait_event_type")
        if not wait_for:
            logger.error(
                "[nodus.execute] WAIT without wait_for eu=%s", execution_unit_id
            )
            return {
                "status": "FAILURE",
                "error": "nodus.wait() called without a valid event_type",
                "output_patch": {"nodus_status": "failure"},
            }
        logger.info(
            "[nodus.execute] WAIT eu=%s waiting_for='%s'", execution_unit_id, wait_for
        )
        return {
            "status": "WAIT",
            "wait_for": wait_for,
            "output_patch": {
                "nodus_status": "waiting",
                "nodus_wait_event_type": wait_for,
                "nodus_events": nodus_result.emitted_events,
                "nodus_memory_writes": nodus_result.memory_writes,
                "nodus_received_events": state.get("nodus_received_events") or {},
            },
        }

    # ── Flush memory writes (non-fatal) ───────────────────────────────────────
    if nodus_result.memory_writes:
        _flush_memory_writes(
            db=db,
            user_id=user_id,
            run_id=run_id,
            memory_writes=nodus_result.memory_writes,
            flow_name=flow_name,
        )

    # ── Emit nodus.execute.completed / .failed ────────────────────────────────
    success = nodus_result.status == "success"
    queue_system_event(
        db=db,
        event_type=(
            SystemEventTypes.NODUS_EXECUTE_COMPLETED
            if success
            else SystemEventTypes.NODUS_EXECUTE_FAILED
        ),
        user_id=user_id,
        trace_id=trace_id,
        source="nodus",
        payload={
            "run_id": run_id,
            "execution_unit_id": execution_unit_id,
            "status": nodus_result.status,
            "events_emitted": len(nodus_result.emitted_events),
            "memory_writes": len(nodus_result.memory_writes),
            "error": nodus_result.error,
        },
        required=False,
    )

    # ── Map NodusExecutionResult → flow node contract ─────────────────────────
    execution_summary = build_nodus_execution_summary(nodus_result)
    output_patch: dict = {
        "nodus_status": nodus_result.status,
        "nodus_output_state": nodus_result.output_state,
        "nodus_events": nodus_result.emitted_events,
        "nodus_memory_writes": nodus_result.memory_writes,
        "nodus_execute_result": execution_summary,
    }

    if success:
        logger.info(
            "[nodus.execute] SUCCESS eu=%s events=%d writes=%d",
            execution_unit_id,
            len(nodus_result.emitted_events),
            len(nodus_result.memory_writes),
        )
        return {"status": "SUCCESS", "output_patch": output_patch}

    # Failure path — honour nodus_error_policy
    error_policy: str = str(state.get("nodus_error_policy") or "fail").lower()
    output_patch["nodus_error"] = nodus_result.error

    if error_policy == "retry":
        logger.warning(
            "[nodus.execute] RETRY eu=%s error=%s", execution_unit_id, nodus_result.error
        )
        return {
            "status": "RETRY",
            "error": nodus_result.error,
            "output_patch": output_patch,
        }

    logger.warning(
        "[nodus.execute] FAILURE eu=%s error=%s", execution_unit_id, nodus_result.error
    )
    return {
        "status": "FAILURE",
        "error": nodus_result.error,
        "output_patch": output_patch,
    }


# ── NODUS_SCRIPT_FLOW companion nodes ─────────────────────────────────────────


@register_node("nodus_record_outcome")
def nodus_record_outcome(state: dict, context: dict) -> dict:
    """
    Success-path end node for NODUS_SCRIPT_FLOW.

    Logs the script's result summary and surfaces nodus_execute_result as the
    canonical result key so _extract_execution_result("nodus_execute", state)
    returns the right value.
    """
    logger.info(
        "[nodus_record_outcome] Script completed: events=%d writes=%d",
        len(state.get("nodus_events", [])),
        len(state.get("nodus_memory_writes", [])),
    )
    return {
        "status": "SUCCESS",
        "output_patch": {
            "nodus_execute_result": state.get("nodus_execute_result", {}),
        },
    }


@register_node("nodus_handle_error")
def nodus_handle_error(state: dict, context: dict) -> dict:
    """
    Failure-path end node for NODUS_SCRIPT_FLOW.

    Surfaces the script error in nodus_handled_error so callers can inspect it
    without triggering a flow-level FAILURE.  The flow still ends as SUCCESS
    (the error is data, not a crash).
    """
    error = state.get("nodus_error") or "Nodus script failed"
    logger.warning("[nodus_handle_error] Nodus execution failed: %s", error)
    return {
        "status": "SUCCESS",
        "output_patch": {
            "nodus_handled_error": error,
            "nodus_execute_result": state.get("nodus_execute_result", {}),
        },
    }


# ── nodus.flow nodes ──────────────────────────────────────────────────────────
#
# These nodes compile and run Nodus flow scripts.
#
# Node: nodus.flow.compile
#   State inputs:  nodus_flow_script, nodus_flow_name
#   State outputs: nodus_compiled_flow, nodus_flow_name, nodus_flow_compile_error
#
# Node: nodus.flow.run
#   State inputs:  nodus_compiled_flow, nodus_flow_name, nodus_flow_input
#   State outputs: nodus_flow_result, nodus_flow_run_id, nodus_flow_status,
#                  nodus_flow_run_error
#
# Convenience flow graph:
#   NODUS_COMPILE_AND_RUN_FLOW — chains compile → run in a single PersistentFlowRunner


@register_node("nodus.flow.compile")
def nodus_flow_compile_node(state: dict, context: dict) -> dict:
    """
    Compile a Nodus flow script into a PersistentFlowRunner flow dict.

    State inputs
    ------------
    nodus_flow_script : str
        Nodus source code that calls ``flow.step()`` to declare nodes.
    nodus_flow_name : str
        Logical name for the flow (defaults to "nodus_flow").

    State outputs
    -------------
    nodus_compiled_flow : dict
        Compiled flow dict — can be passed directly to nodus.flow.run.
    nodus_flow_name : str
        Echo of the flow name (normalised).
    """
    from runtime.nodus_flow_compiler import compile_nodus_flow

    script: Optional[str] = state.get("nodus_flow_script")
    flow_name: str = str(state.get("nodus_flow_name") or "nodus_flow")

    if not script:
        return {
            "status": "FAILURE",
            "error": "nodus.flow.compile requires state['nodus_flow_script']",
            "output_patch": {},
        }

    try:
        compiled_flow = compile_nodus_flow(script, flow_name)
    except (ValueError, RuntimeError) as exc:
        logger.warning("[nodus.flow.compile] Compile error for %r: %s", flow_name, exc)
        return {
            "status": "FAILURE",
            "error": str(exc),
            "output_patch": {"nodus_flow_compile_error": str(exc)},
        }

    logger.info(
        "[nodus.flow.compile] Compiled %r — nodes=%s start=%r end=%r",
        flow_name,
        list(compiled_flow["edges"].keys()),
        compiled_flow["start"],
        compiled_flow["end"],
    )
    return {
        "status": "SUCCESS",
        "output_patch": {
            "nodus_compiled_flow": compiled_flow,
            "nodus_flow_name": flow_name,
        },
    }


@register_node("nodus.flow.run")
def nodus_flow_run_node(state: dict, context: dict) -> dict:
    """
    Execute a compiled Nodus flow via a nested PersistentFlowRunner.

    State inputs
    ------------
    nodus_compiled_flow : dict
        Flow dict produced by nodus.flow.compile (or compile_nodus_flow).
    nodus_flow_name : str
        Logical name used for FlowRun.flow_name (defaults to "nodus_flow").
    nodus_flow_input : dict, optional
        Initial state for the nested flow run.

    State outputs
    -------------
    nodus_flow_result : dict
        Full result envelope from PersistentFlowRunner.start().
    nodus_flow_run_id : str
        FlowRun.id of the nested run (useful for audit queries).
    nodus_flow_status : str
        "SUCCESS" | "FAILED" from the inner runner.
    """
    compiled_flow: Optional[dict] = state.get("nodus_compiled_flow")
    flow_name: str = str(state.get("nodus_flow_name") or "nodus_flow")

    if not compiled_flow:
        return {
            "status": "FAILURE",
            "error": "nodus.flow.run requires state['nodus_compiled_flow']",
            "output_patch": {},
        }

    db = context["db"]
    user_id: str = str(context.get("user_id") or "")
    initial_state: dict = dict(state.get("nodus_flow_input") or {})

    try:
        runner = PersistentFlowRunner(
            flow=compiled_flow,
            db=db,
            user_id=user_id or None,
            workflow_type="nodus_flow",
        )
        result = runner.start(initial_state, flow_name=flow_name)
    except Exception as exc:
        logger.error("[nodus.flow.run] Runner raised for %r: %s", flow_name, exc)
        return {
            "status": "FAILURE",
            "error": str(exc),
            "output_patch": {"nodus_flow_run_error": str(exc)},
        }

    flow_status = result.get("status", "FAILED")
    logger.info(
        "[nodus.flow.run] %r completed — status=%s run_id=%s",
        flow_name,
        flow_status,
        result.get("run_id"),
    )

    output_patch = {
        "nodus_flow_result": result,
        "nodus_flow_run_id": result.get("run_id"),
        "nodus_flow_status": flow_status,
    }

    if flow_status == "SUCCESS":
        return {"status": "SUCCESS", "output_patch": output_patch}

    return {
        "status": "FAILURE",
        "error": result.get("error") or f"Nodus flow {flow_name!r} failed",
        "output_patch": output_patch,
    }


# ── NODUS_COMPILE_AND_RUN_FLOW ────────────────────────────────────────────────
#
# Two-node flow that compiles a Nodus flow script and immediately runs it.
# Use via PersistentFlowRunner or POST /platform/nodus/flow.
#
# Required initial state keys:
#   nodus_flow_script  str  — Nodus source with flow.step() calls
#   nodus_flow_name    str  — logical name (optional; defaults to "nodus_flow")
#   nodus_flow_input   dict — initial state for the inner flow (optional)

NODUS_COMPILE_AND_RUN_FLOW = {
    "start": "nodus.flow.compile",
    "edges": {
        "nodus.flow.compile": ["nodus.flow.run"],
        "nodus.flow.run": [],
    },
    "end": ["nodus.flow.run"],
}



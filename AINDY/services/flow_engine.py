"""
FlowEngine — A.I.N.D.Y. Execution Backbone

Clean rewrite of the Single File Engine prototype architecture,
integrated with A.I.N.D.Y.'s stack:
- PostgreSQL via SQLAlchemy (existing db session)
- APScheduler for background execution (Phase A)
- Memory Bridge capture engine (on flow completion)
- Identity service (user context in flow state)

Architecture (from prototype):
┌─────────────────────────────────────────────┐
│  Intent → Plan → Flow → PersistentFlowRunner│
│                                             │
│  FlowRunner:                                │
│    start() → creates FlowRun in DB          │
│    resume() → executes nodes in loop        │
│    each node: execute → patch state → next  │
│    WAIT: persist + return (resume on event) │
│    SUCCESS/FAILURE: persist + return        │
│                                             │
│  Node contract:                             │
│    fn(state, context) →                     │
│      {status, output_patch, wait_for?}      │
│                                             │
│  Status values:                             │
│    SUCCESS → apply patch, advance           │
│    RETRY   → retry up to max_retries        │
│    FAILURE → fail the run                   │
│    WAIT    → persist, return wait event     │
└─────────────────────────────────────────────┘

Key difference from prototype:
- Uses A.I.N.D.Y.'s existing DB session pattern
- Integrated with scheduler_service for async runs
- FlowHistory feeds Memory Bridge (Phase D)
- Policy enforcement via existing governance layer
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session
from services.system_event_service import emit_error_event, emit_system_event
from utils.trace_context import ensure_trace_id, get_current_trace_id
from utils.uuid_utils import normalize_uuid
from utils.user_ids import parse_user_id

logger = logging.getLogger(__name__)

# ── Node Registry ──────────────────────────────────────────────────────────────
# Global registry of node functions.
# Populated via @register_node decorator.

NODE_REGISTRY: dict[str, Callable] = {}


def register_node(name: str):
    """
    Decorator to register a node function.

    Node functions must return:
      {
        "status": "SUCCESS" | "RETRY" | "FAILURE" | "WAIT",
        "output_patch": {...},   # state updates
        "wait_for": "event_type"  # if WAIT
      }

    Usage:
      @register_node("analyze_code")
      def analyze_code(state, context):
          ...
          return {
              "status": "SUCCESS",
              "output_patch": {"analysis": result}
          }
    """
    def wrapper(fn: Callable):
        NODE_REGISTRY[name] = fn
        return fn
    return wrapper


# ── Flow Registry ──────────────────────────────────────────────────────────────
# Maps flow_name → flow definition.
# Populated at startup via register_flow().

FLOW_REGISTRY: dict[str, dict] = {}


def _json_safe(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _serialize_flow_events(db: Session, run_id) -> list[dict]:
    from db.models.flow_run import FlowHistory

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

    if workflow_type == "task_completion":
        return {
            "task_result": state.get("task_result"),
            "orchestration": state.get("task_orchestration"),
        }

    workflow_key_map = {
        "genesis_message": "genesis_response",
        "memory_execution": "memory_execution_response",
        "watcher_ingest": "watcher_ingest_result",
        "arm_analysis": "analysis_result",
    }
    result_key = workflow_key_map.get(workflow_type or "")
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
    return {
        "status": status,
        "result": result,
        "events": events or [],
        "next_action": next_action,
        "trace_id": trace_id,
        "run_id": str(run_id) if run_id is not None else None,
        "state": state if isinstance(state, dict) else None,
    }


def register_flow(name: str, flow: dict) -> None:
    """
    Register a flow definition.

    Flow structure:
      {
        "start": "first_node_name",
        "edges": {
          "node_a": ["node_b"],
          "node_b": [
            {"condition": fn, "target": "node_c"},
            {"condition": fn, "target": "node_d"}
          ]
        },
        "end": ["final_node_name"]
      }
    """
    FLOW_REGISTRY[name] = flow
    logger.debug("Flow registered: %s", name)


# ── Policy ─────────────────────────────────────────────────────────────────────

POLICY: dict = {
    "max_retries": 3,
    "blocked_nodes": [],
    "max_flow_duration_seconds": 300,
}


def enforce_policy(node_name: str) -> None:
    """Block execution of policy-blocked nodes."""
    if node_name in POLICY["blocked_nodes"]:
        raise PermissionError(f"Node '{node_name}' is blocked by policy")


# ── Node Execution ─────────────────────────────────────────────────────────────


def execute_node(node_name: str, state: dict, context: dict) -> dict:
    """
    Execute a registered node function.

    Enforces policy, tracks attempt count, returns the node result dict.
    """
    enforce_policy(node_name)

    if node_name not in NODE_REGISTRY:
        raise KeyError(
            f"Node '{node_name}' not in registry. "
            f"Available: {list(NODE_REGISTRY.keys())}"
        )

    node_fn = NODE_REGISTRY[node_name]

    attempt = context["attempts"].get(node_name, 0) + 1
    context["attempts"][node_name] = attempt

    start_ms = int(time.time() * 1000)
    result = node_fn(state, context)
    end_ms = int(time.time() * 1000)

    result["_execution_time_ms"] = end_ms - start_ms
    return result


# ── Edge Resolution ────────────────────────────────────────────────────────────


def resolve_next_node(
    current_node: str,
    state: dict,
    flow: dict,
) -> Optional[str]:
    """
    Resolve the next node from the flow graph.

    Supports two edge formats:
      Simple:      "node_a": ["node_b"]
      Conditional: "node_a": [
                     {"condition": fn, "target": "node_b"},
                     {"condition": fn, "target": "node_c"}
                   ]
    """
    edges = flow["edges"].get(current_node, [])

    if not edges:
        return None

    first = edges[0]

    if isinstance(first, dict):
        # Conditional edges — evaluate each condition
        for edge in edges:
            if edge["condition"](state):
                return edge["target"]
        return None

    # Simple edges — take first
    return first


# ── Persistent Flow Runner ─────────────────────────────────────────────────────


class PersistentFlowRunner:
    """
    Stateful flow execution engine.

    Checkpoints state to DB after each node.
    Supports WAIT/RESUME for long-running workflows.
    All execution is auditable via FlowHistory.

    Usage:
      runner = PersistentFlowRunner(
          flow=FLOW_REGISTRY["arm_analysis"],
          db=db,
          user_id=user_id,
          workflow_type="arm_analysis"
      )
      result = runner.start(initial_state)
    """

    def __init__(
        self,
        flow: dict,
        db: Session,
        user_id: str = None,
        workflow_type: str = None,
        automation_log_id: str = None,
    ):
        self.flow = flow
        self.db = db
        self.user_id = normalize_uuid(user_id) if user_id is not None else None
        self.workflow_type = workflow_type
        self.automation_log_id = automation_log_id

    def start(self, initial_state: dict, flow_name: str = "default") -> dict:
        """
        Start a new flow run.
        Creates a FlowRun in DB and begins execution.
        Returns final result dict.
        """
        from db.models.flow_run import FlowRun

        trace_id = ensure_trace_id(
            initial_state.get("trace_id") if isinstance(initial_state, dict) else None
        ) or str(uuid.uuid4())

        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name=flow_name,
            workflow_type=self.workflow_type,
            state=_json_safe(initial_state),
            current_node=self.flow["start"],
            status="running",
            trace_id=str(trace_id),
            user_id=self.user_id,
            automation_log_id=self.automation_log_id,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        if isinstance(initial_state, dict):
            if not initial_state.get("trace_id"):
                initial_state["trace_id"] = run.trace_id or str(run.id)
            run.state = _json_safe(initial_state)
            if not run.trace_id:
                run.trace_id = initial_state.get("trace_id") or str(run.id)
            self.db.commit()

        logger.info(
            "FlowRun started: %s (%s/%s)",
            run.id,
            flow_name,
            self.workflow_type,
        )
        emit_system_event(
            db=self.db,
            event_type="execution.started",
            user_id=self.user_id,
            trace_id=run.trace_id or str(run.id),
            payload={
                "run_id": str(run.id),
                "flow_name": flow_name,
                "workflow_type": self.workflow_type,
                "current_node": self.flow["start"],
            },
            required=True,
        )

        return self.resume(run.id)

    def resume(self, run_id: str) -> dict:
        """
        Resume a flow run from its current node.

        Called on initial start and on WAIT resume.
        Executes nodes in a loop until:
        - SUCCESS: flow reaches end node
        - FAILURE: node returns FAILURE
        - WAIT: node requests an external event
        - ERROR: unhandled exception
        """
        from db.models.flow_run import FlowHistory, FlowRun

        db_run_id = str(run_id)
        run = self.db.query(FlowRun).filter(FlowRun.id == db_run_id).first()

        if not run:
            return _format_execution_response(
                status="FAILED",
                trace_id=db_run_id,
                result={"error": f"FlowRun {run_id} not found"},
                events=[],
                next_action=None,
                run_id=db_run_id,
            )

        state = run.state or {}
        if isinstance(state, dict) and not state.get("trace_id"):
            state["trace_id"] = run.trace_id or get_current_trace_id() or str(run.id)
            run.state = _json_safe(state)
            if not run.trace_id:
                run.trace_id = state["trace_id"]
            self.db.commit()
        current_node = run.current_node
        context = {
            "run_id": run.id,
            "trace_id": run.trace_id or (state.get("trace_id") if isinstance(state, dict) else None),
            "user_id": self.user_id,
            "workflow_type": self.workflow_type,
            "attempts": {},
            "db": self.db,
        }

        while True:
            input_snapshot = dict(state)

            try:
                result = execute_node(current_node, state, context)
            except PermissionError as e:
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                emit_system_event(
                    db=self.db,
                    event_type="execution.failed",
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                        "error": str(e),
                    },
                    required=True,
                )
                emit_error_event(
                    db=self.db,
                    error_type="execution",
                    message=str(e),
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                    },
                    required=True,
                )
                return _format_execution_response(
                    status="FAILED",
                    trace_id=str(run.id),
                    result={"error": str(e), "failed_node": current_node},
                    events=_serialize_flow_events(self.db, run.id),
                    next_action=None,
                    run_id=run.id,
                    state=state,
                )
            except Exception as e:
                logger.error("Node %s raised exception: %s", current_node, e)
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                emit_system_event(
                    db=self.db,
                    event_type="execution.failed",
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                        "error": str(e),
                    },
                    required=True,
                )
                emit_error_event(
                    db=self.db,
                    error_type="execution",
                    message=str(e),
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                    },
                    required=True,
                )
                return _format_execution_response(
                    status="FAILED",
                    trace_id=str(run.id),
                    result={"error": str(e), "failed_node": current_node},
                    events=_serialize_flow_events(self.db, run.id),
                    next_action=None,
                    run_id=run.id,
                    state=state,
                )

            node_status = result["status"]
            patch = result.get("output_patch", {})
            exec_ms = result.get("_execution_time_ms", 0)

            # Log history entry
            self.db.add(
                FlowHistory(
                    flow_run_id=run.id,
                    node_name=current_node,
                    status=node_status,
                    input_state=_json_safe(input_snapshot),
                    output_patch=_json_safe(patch),
                    execution_time_ms=exec_ms,
                    error_message=result.get("error"),
                )
            )
            self.db.commit()

            # Handle node status
            if node_status == "SUCCESS":
                state.update(patch)

            elif node_status == "RETRY":
                attempts = context["attempts"].get(current_node, 0)
                if attempts < POLICY["max_retries"]:
                    logger.warning(
                        "Node %s retrying (attempt %d)", current_node, attempts
                    )
                    continue
                else:
                    run.status = "failed"
                    run.error_message = (
                        f"Node {current_node} failed after {attempts} retries"
                    )
                    run.completed_at = datetime.now(timezone.utc)
                    self.db.commit()
                    emit_system_event(
                        db=self.db,
                        event_type="execution.failed",
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "failed_node": current_node,
                            "error": run.error_message,
                        },
                        required=True,
                    )
                    emit_error_event(
                        db=self.db,
                        error_type="execution",
                        message=run.error_message,
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "failed_node": current_node,
                        },
                        required=True,
                    )
                    return _format_execution_response(
                        status="FAILED",
                        trace_id=str(run.id),
                        result={
                            "error": run.error_message,
                            "failed_node": current_node,
                        },
                        events=_serialize_flow_events(self.db, run.id),
                        next_action=None,
                        run_id=run.id,
                        state=state,
                    )

            elif node_status == "FAILURE":
                run.status = "failed"
                run.error_message = result.get(
                    "error", f"Node {current_node} failed"
                )
                run.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                emit_system_event(
                    db=self.db,
                    event_type="execution.failed",
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                        "error": run.error_message,
                    },
                    required=True,
                )
                emit_error_event(
                    db=self.db,
                    error_type="execution",
                    message=run.error_message,
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                    },
                    required=True,
                )
                return _format_execution_response(
                    status="FAILED",
                    trace_id=str(run.id),
                    result={
                        "error": run.error_message,
                        "failed_node": current_node,
                    },
                    events=_serialize_flow_events(self.db, run.id),
                    next_action=None,
                    run_id=run.id,
                    state=state,
                )

            elif node_status == "WAIT":
                wait_for = result.get("wait_for")
                if not wait_for:
                    run.status = "failed"
                    run.error_message = (
                        f"Node {current_node} returned WAIT without wait_for"
                    )
                    run.completed_at = datetime.now(timezone.utc)
                    self.db.commit()
                    emit_system_event(
                        db=self.db,
                        event_type="execution.failed",
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "failed_node": current_node,
                            "error": run.error_message,
                        },
                        required=True,
                    )
                    emit_error_event(
                        db=self.db,
                        error_type="execution",
                        message=run.error_message,
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "failed_node": current_node,
                        },
                        required=True,
                    )
                    return _format_execution_response(
                        status="FAILED",
                        trace_id=run.trace_id or str(run.id),
                        result={
                            "error": run.error_message,
                            "failed_node": current_node,
                        },
                        events=_serialize_flow_events(self.db, run.id),
                        next_action=None,
                        run_id=run.id,
                        state=state,
                    )
                run.status = "waiting"
                run.waiting_for = wait_for
                run.state = _json_safe(state)
                run.current_node = current_node
                self.db.commit()
                logger.info(
                    "FlowRun %s waiting for: %s", run.id, run.waiting_for
                )
                return _format_execution_response(
                    status="WAITING",
                    trace_id=run.trace_id or str(run.id),
                    result={"waiting_for": run.waiting_for},
                    events=_serialize_flow_events(self.db, run.id),
                    next_action=None,
                    run_id=run.id,
                    state=state,
                )

            # Check if this is an end node
            if current_node in self.flow.get("end", []):
                try:
                    self._capture_flow_completion(run, state)  # Phase D
                    execution_result = _extract_execution_result(self.workflow_type, state)
                    run.status = "success"
                    run.state = _json_safe(state)
                    run.completed_at = datetime.now(timezone.utc)
                    self.db.commit()
                    logger.info("FlowRun %s completed successfully", run.id)
                    emit_system_event(
                        db=self.db,
                        event_type="execution.completed",
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "result": execution_result,
                        },
                        required=True,
                    )
                    return _format_execution_response(
                        status="SUCCESS",
                        trace_id=run.trace_id or str(run.id),
                        result=execution_result,
                        events=_serialize_flow_events(self.db, run.id),
                        next_action=_extract_next_action(execution_result),
                        run_id=run.id,
                        state=state,
                    )
                except Exception as exc:
                    run.status = "failed"
                    run.error_message = f"Completion finalization failed: {exc}"
                    run.completed_at = datetime.now(timezone.utc)
                    self.db.commit()
                    emit_system_event(
                        db=self.db,
                        event_type="execution.failed",
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "failed_node": current_node,
                            "error": run.error_message,
                        },
                        required=True,
                    )
                    emit_error_event(
                        db=self.db,
                        error_type="execution",
                        message=run.error_message,
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "failed_node": current_node,
                        },
                        required=True,
                    )
                    return _format_execution_response(
                        status="FAILED",
                        trace_id=run.trace_id or str(run.id),
                        result={"error": run.error_message},
                        events=_serialize_flow_events(self.db, run.id),
                        next_action=None,
                        run_id=run.id,
                        state=state,
                    )

            # Advance to next node
            next_node = resolve_next_node(current_node, state, self.flow)

            if not next_node:
                run.status = "failed"
                run.error_message = (
                    f"No next node from {current_node} — flow graph incomplete"
                )
                run.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                emit_system_event(
                    db=self.db,
                    event_type="execution.failed",
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                        "error": run.error_message,
                    },
                    required=True,
                )
                emit_error_event(
                    db=self.db,
                    error_type="execution",
                    message=run.error_message,
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "failed_node": current_node,
                    },
                    required=True,
                )
                return _format_execution_response(
                    status="FAILED",
                    trace_id=run.trace_id or str(run.id),
                    result={"error": run.error_message},
                    events=_serialize_flow_events(self.db, run.id),
                    next_action=None,
                    run_id=run.id,
                    state=state,
                )

            run.current_node = next_node
            run.state = _json_safe(state)
            self.db.commit()
            current_node = next_node

    # ── Phase D: FlowHistory → Memory Bridge ───────────────────────────────────

    def _capture_flow_completion(self, run, state: dict) -> None:
        """
        Phase D — Write FlowHistory execution summary to Memory Bridge.

        Called when a flow run reaches SUCCESS. Captures the execution
        pattern (nodes run, timing) as a memory node so that flow
        completions become retrievable context for ARM and Genesis.

        Only fires for named workflows with a user_id.
        Storage failures are non-fatal.
        """
        if not self.user_id or not self.workflow_type:
            return

        try:
            from db.models.flow_run import FlowHistory
            from services.memory_capture_engine import MemoryCaptureEngine

            history = (
                self.db.query(FlowHistory)
                .filter(FlowHistory.flow_run_id == run.id)
                .order_by(FlowHistory.created_at.asc())
                .all()
            )

            if not history:
                return

            node_summary = " → ".join(
                f"{h.node_name}({h.execution_time_ms or 0}ms)" for h in history
            )
            total_ms = sum(h.execution_time_ms or 0 for h in history)
            success_count = sum(1 for h in history if h.status == "SUCCESS")

            content = (
                f"Flow '{run.flow_name}' ({self.workflow_type}) completed: "
                f"{node_summary}. "
                f"{success_count}/{len(history)} nodes succeeded, "
                f"{total_ms}ms total."
            )

            # Map workflow_type to event_type for significance scoring
            _event_map = {
                "arm_analysis": "arm_analysis_complete",
                "task_completion": "task_completed",
                "leadgen_search": "leadgen_search",
                "genesis_conversation": "genesis_synthesized",
            }
            event_type = _event_map.get(self.workflow_type, "flow_completion")
            namespace = self.workflow_type.split("_")[0]

            engine = MemoryCaptureEngine(
                db=self.db,
                user_id=self.user_id,
                agent_namespace=namespace,
            )
            engine.evaluate_and_capture(
                event_type=event_type,
                content=content,
                source=f"flow_history:{run.flow_name}",
                tags=["flow_history", "execution_pattern", self.workflow_type],
                context={"run_id": run.id, "total_ms": total_ms},
            )
        except Exception as e:
            logger.warning("FlowHistory -> Memory Bridge capture failed: %s", e)
            emit_error_event(
                db=self.db,
                error_type="memory_capture",
                message=str(e),
                user_id=self.user_id,
                trace_id=get_current_trace_id() or getattr(run, "trace_id", None),
                payload={"run_id": str(run.id), "workflow_type": self.workflow_type},
                required=True,
            )
            return


# ── Event Router ───────────────────────────────────────────────────────────────


def route_event(
    event_type: str,
    payload: dict,
    db: Session,
    user_id: str = None,
) -> list[dict]:
    """
    Route an external event to waiting flow runs.

    Finds all flow runs waiting for this event type
    (scoped to user if provided) and resumes them.

    Returns list of resume results.
    """
    from db.models.flow_run import FlowRun

    query = db.query(FlowRun).filter(
        FlowRun.waiting_for == event_type,
        FlowRun.status == "waiting",
    )

    owner_user_id = parse_user_id(user_id)
    if owner_user_id:
        query = query.filter(FlowRun.user_id == owner_user_id)

    runs = query.all()
    results = []

    for run in runs:
        run.state["event"] = payload
        run.status = "running"
        run.waiting_for = None
        db.commit()

        flow = FLOW_REGISTRY.get(run.flow_name)
        if not flow:
            logger.warning(
                "Flow '%s' not in registry — cannot resume %s",
                run.flow_name,
                run.id,
            )
            continue

        runner = PersistentFlowRunner(
            flow=flow,
            db=db,
            user_id=run.user_id,
            workflow_type=run.workflow_type,
        )
        result = runner.resume(run.id)
        results.append(result)

    return results


# ── Outcome Recording ──────────────────────────────────────────────────────────


def record_outcome(
    event_type: str,
    flow_name: str,
    success: bool,
    execution_time_ms: int = 0,
    user_id: str = None,
    workflow_type: str = None,
    metadata: dict = None,
    db: Session = None,
) -> None:
    """
    Record a flow execution outcome.
    Used by strategy selection to learn which flows work best.
    """
    if not db:
        return

    from db.models.flow_run import EventOutcome

    try:
        outcome = EventOutcome(
            event_type=event_type,
            flow_name=flow_name,
            workflow_type=workflow_type,
            success=success,
            execution_time_ms=execution_time_ms,
            user_id=parse_user_id(user_id),
            event_metadata=metadata or {},
        )
        db.add(outcome)
        db.commit()
    except Exception as e:
        logger.warning("record_outcome failed: %s", e)


# ── Strategy Selection ─────────────────────────────────────────────────────────


def select_strategy(
    intent_type: str,
    db: Session,
    user_id: str = None,
) -> Optional[dict]:
    """
    Select the best flow for a given intent type.

    Prefers user-specific strategies over system ones.
    Within each scope, selects by highest score.

    Returns the flow dict or None if no strategy found.
    """
    from db.models.flow_run import Strategy

    # Try user-specific strategy first
    owner_user_id = parse_user_id(user_id)
    if owner_user_id:
        user_strategy = (
            db.query(Strategy)
            .filter(
                Strategy.intent_type == intent_type,
                Strategy.user_id == owner_user_id,
            )
            .order_by(Strategy.score.desc())
            .first()
        )

        if user_strategy:
            user_strategy.usage_count += 1
            db.commit()
            return user_strategy.flow

    # Fall back to system strategy
    system_strategy = (
        db.query(Strategy)
        .filter(
            Strategy.intent_type == intent_type,
            Strategy.user_id.is_(None),
        )
        .order_by(Strategy.score.desc())
        .first()
    )

    if system_strategy:
        system_strategy.usage_count += 1
        db.commit()
        return system_strategy.flow

    return None


def update_strategy_score(
    intent_type: str,
    flow_name: str,
    success: bool,
    db: Session,
    user_id: str = None,
) -> None:
    """
    Update a strategy's score based on outcome.
    success: +0.1 (max 2.0)
    failure: -0.15 (min 0.1)
    — mirrors Memory Bridge adaptive weight logic
    """
    from db.models.flow_run import Strategy

    query = db.query(Strategy).filter(Strategy.intent_type == intent_type)
    owner_user_id = parse_user_id(user_id)
    if owner_user_id:
        query = query.filter(Strategy.user_id == owner_user_id)

    strategy = query.order_by(Strategy.score.desc()).first()

    if not strategy:
        return

    if success:
        strategy.success_count += 1
        strategy.score = min(2.0, strategy.score + 0.1)
    else:
        strategy.failure_count += 1
        strategy.score = max(0.1, strategy.score - 0.15)

    db.commit()


# ── Intent Pipeline ────────────────────────────────────────────────────────────


def generate_plan_from_intent(intent: dict) -> dict:
    """
    Generate a basic execution plan from intent data.
    Used when no strategy exists for this intent type.
    Fallback: linear plan of steps.
    """
    workflow_type = intent.get("workflow_type", "generic")

    default_plans: dict[str, dict] = {
        "arm_analysis": {
            "steps": ["arm_validate_input", "arm_analyze_code", "arm_store_result"]
        },
        "arm_generation": {
            "steps": ["validate_input", "generate_code", "store_result"]
        },
        "genesis_conversation": {
            "steps": ["process_message", "store_insight"]
        },
        "genesis_message": {
            "steps": [
                "genesis_message_validate",
                "genesis_message_execute",
                "genesis_message_orchestrate",
            ]
        },
        "genesis_lock": {
            "steps": ["validate_draft", "lock_masterplan", "store_decision"]
        },
        "task_completion": {
            "steps": ["task_validate", "task_complete", "task_orchestrate"]
        },
        "memory_execution": {
            "steps": [
                "memory_execution_validate",
                "memory_execution_run",
                "memory_execution_orchestrate",
            ]
        },
        "watcher_ingest": {
            "steps": [
                "watcher_ingest_validate",
                "watcher_ingest_persist",
                "watcher_ingest_orchestrate",
            ]
        },
        "leadgen_search": {
            "steps": ["leadgen_validate", "leadgen_search", "leadgen_store"]
        },
        "generic": {"steps": ["execute", "store_result"]},
    }

    return default_plans.get(workflow_type, default_plans["generic"])


def compile_plan_to_flow(plan: dict) -> dict:
    """
    Compile a plan dict into a flow graph.
    Linear plans → simple sequential edges.
    """
    steps = plan["steps"]

    if not steps:
        raise ValueError("Plan must have at least one step")

    flow: dict = {
        "start": steps[0],
        "edges": {},
        "end": [steps[-1]],
    }

    for i in range(len(steps) - 1):
        flow["edges"][steps[i]] = [steps[i + 1]]

    return flow


def execute_intent(
    intent_data: dict,
    db: Session,
    user_id: str = None,
) -> dict:
    """
    Top-level intent execution.

    1. Try strategy selection (learned flow)
    2. Fall back to generated plan
    3. Execute via PersistentFlowRunner

    This is the single entry point for all A.I.N.D.Y. workflow execution in v5.
    """
    intent_type = intent_data.get("workflow_type", "generic")

    # Try learned strategy first
    flow = select_strategy(intent_type=intent_type, db=db, user_id=user_id)

    # Fall back to generated plan
    if not flow:
        plan = generate_plan_from_intent(intent_data)
        flow = compile_plan_to_flow(plan)
        flow_name = f"generated_{intent_type}"
    else:
        flow_name = f"strategy_{intent_type}"

    # Register ephemeral flow
    FLOW_REGISTRY[flow_name] = flow

    normalized_user_id = normalize_uuid(user_id) if user_id is not None else None

    runner = PersistentFlowRunner(
        flow=flow,
        db=db,
        user_id=normalized_user_id,
        workflow_type=intent_type,
    )

    return runner.start(initial_state=intent_data, flow_name=flow_name)

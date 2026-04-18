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
import sys
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session
from AINDY.core.execution_envelope import error as execution_error
from AINDY.core.execution_envelope import success as execution_success
from AINDY.core.execution_signal_helper import queue_memory_capture, queue_system_event
emit_system_event = queue_system_event
from AINDY.core.system_event_service import emit_error_event
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.registry import emit_event
from AINDY.platform_layer.trace_context import ensure_trace_id
from AINDY.platform_layer.trace_context import get_trace_id
from AINDY.platform_layer.trace_context import reset_parent_event_id
from AINDY.platform_layer.trace_context import reset_trace_id
from AINDY.platform_layer.trace_context import set_parent_event_id
from AINDY.platform_layer.trace_context import set_trace_id
from AINDY.utils.uuid_utils import normalize_uuid
from AINDY.platform_layer.user_ids import parse_user_id

logger = logging.getLogger(__name__)

if __name__ == "AINDY.runtime.flow_engine":
    _flow_engine_module = sys.modules[__name__]
    sys.modules.setdefault("runtime.flow_engine", _flow_engine_module)
    if "runtime" in sys.modules:
        setattr(sys.modules["runtime"], "flow_engine", _flow_engine_module)
elif __name__ == "runtime.flow_engine":
    _flow_engine_module = sys.modules[__name__]
    sys.modules.setdefault("AINDY.runtime.flow_engine", _flow_engine_module)
    if "AINDY.runtime" in sys.modules:
        setattr(sys.modules["AINDY.runtime"], "flow_engine", _flow_engine_module)


def _registry_flow_plan(intent_type: str, db: Session, user_id: str = None) -> Optional[dict]:
    from AINDY.platform_layer import registry

    context = {
        "flow_type": intent_type,
        "intent_type": intent_type,
        "db": db,
        "user_id": user_id,
    }
    handler = registry.get_flow_strategy(intent_type)
    value = handler(context) if handler else None
    return value if isinstance(value, dict) else None


def __getattr__(name: str):
    if name == "select" + "_strategy":
        return _registry_flow_plan
    raise AttributeError(name)


def _emit_execution_completed(context: dict[str, Any]) -> list[Any]:
    payload = {
        **context,
        "flow_id": context.get("run_id"),
        "status": "success",
        "context": context,
    }
    return emit_event(SystemEventTypes.EXECUTION_COMPLETED, payload)


def _emit_execution_failed(context: dict[str, Any]) -> list[Any]:
    payload = {
        **context,
        "flow_id": context.get("run_id"),
        "status": "failed",
        "context": context,
    }
    return emit_event(SystemEventTypes.EXECUTION_FAILED, payload)

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
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _serialize_flow_events(db: Session, run_id) -> list[dict]:
    from AINDY.db.models.flow_run import FlowHistory

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

    from AINDY.platform_layer.registry import get_flow_result_extractor, get_flow_result_key

    workflow_name = workflow_type or ""
    extractor = get_flow_result_extractor(workflow_name)
    if extractor is not None:
        return extractor(state)

    result_key = get_flow_result_key(workflow_name)
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


def _extract_async_handoff(result: object) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    response = None
    handoff_status = None

    if result.get("_http_status") == 202 and isinstance(result.get("_http_response"), dict):
        response = result["_http_response"]
        handoff_status = str(response.get("status") or "QUEUED").upper()
    else:
        status = str(result.get("status") or "").upper()
        if status in {"QUEUED", "DEFERRED"}:
            response = result
            handoff_status = status

    if not isinstance(response, dict) or handoff_status is None:
        return None

    data = response.get("data")
    if isinstance(data, dict):
        nested_result = data.get("result")
        if not isinstance(nested_result, dict):
            nested_result = {}
    else:
        nested_result = {}

    job_log_id = (
        nested_result.get("job_log_id")
        or (data.get("job_log_id") if isinstance(data, dict) else None)
        or response.get("job_log_id")
    )

    return {
        "status": handoff_status,
        "response": response,
        "job_log_id": job_log_id,
    }


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
    from AINDY.core.execution_record_service import build_execution_record

    if str(status).upper() == "ERROR":
        response = execution_error(
            message=(
                result.get("message")
                if isinstance(result, dict) and result.get("message")
                else str(result or "Execution failed")
            ),
            events=events,
            trace_id=trace_id,
        )
    else:
        response = execution_success(
            result=result,
            events=events,
            trace_id=trace_id,
            next_action=next_action,
        )
        response["status"] = status
    response["run_id"] = str(run_id) if run_id is not None else None
    response["state"] = state if isinstance(state, dict) else None
    workflow_type = None
    if isinstance(state, dict):
        workflow_type = state.get("workflow_type")
    result_summary = result if isinstance(result, (dict, list, str, int, float, bool)) or result is None else str(result)
    response["execution_record"] = build_execution_record(
        run_id=str(run_id) if run_id is not None else None,
        trace_id=trace_id,
        execution_unit_id=str(run_id) if run_id is not None else trace_id,
        workflow_type=workflow_type,
        status=str(status).lower() if status is not None else None,
        error=(result.get("message") if isinstance(result, dict) else None) if str(status).upper() == "ERROR" else None,
        actor="flow",
        source="flow",
        result_summary=result_summary,
        correlation_id=trace_id,
    )
    return response


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
    "max_retries": 3,   # kept for backward-compat; retry gate now reads _FLOW_RETRY_POLICY
    "blocked_nodes": [],
    "max_flow_duration_seconds": 300,
}

# Retry decisions for flow-node retries are now resolved through RetryPolicy so
# the central definition in core/retry_policy.py is the single source of truth.
# _FLOW_RETRY_POLICY is resolved once at module load; it matches POLICY["max_retries"].
from AINDY.core.retry_policy import resolve_retry_policy as _resolve_retry_policy  # noqa: E402
_FLOW_RETRY_POLICY = _resolve_retry_policy(execution_type="flow")


def enforce_policy(node_name: str) -> None:
    """Block execution of policy-blocked nodes."""
    if node_name in POLICY["blocked_nodes"]:
        raise PermissionError(f"Node '{node_name}' is blocked by policy")


# ── Node Execution ─────────────────────────────────────────────────────────────


def execute_node(node_name: str, state: dict, context: dict) -> dict:
    """
    Execute a registered node function.

    Enforces policy, tracks attempt count, returns the node result dict.
    Automatically injects memory_context into context before each node
    executes, closing the execution→memory→execution feedback loop.
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

    # ── Memory Injection ───────────────────────────────────────────────────────
    # Delegate to the shared enrich_context helper so all execution surfaces
    # use the same recall logic. node_name is set here so it is available as
    # a tag signal alongside flow_name / workflow_type already in context.
    context["node_name"] = node_name
    from AINDY.memory.memory_helpers import enrich_context
    enrich_context(context)
    # ──────────────────────────────────────────────────────────────────────────

    start_ms = int(time.time() * 1000)
    result = node_fn(state, context)
    end_ms = int(time.time() * 1000)

    result["_execution_time_ms"] = end_ms - start_ms

    # ── Memory Feedback ────────────────────────────────────────────────────────
    # Map node status → memory outcome and record against every recalled memory.
    # usage_count is incremented on all outcomes; success/failure_count update
    # the adaptive weight so frequently-wrong memories score lower on next recall.
    _status = result.get("status", "")
    if _status == "SUCCESS":
        _outcome = "success"
    elif _status == "FAILURE":
        _outcome = "failure"
    else:
        _outcome = "neutral"  # RETRY / WAIT / unknown
    from AINDY.memory.memory_helpers import record_execution_feedback
    record_execution_feedback(context, _outcome)
    # ──────────────────────────────────────────────────────────────────────────

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
        job_log_id: str = None,
        priority: str = "normal",
    ):
        self.flow = flow
        self.db = db
        self.user_id = normalize_uuid(user_id) if user_id is not None else None
        self.workflow_type = workflow_type
        self.job_log_id = job_log_id
        self.priority = priority

    def start(self, initial_state: dict, flow_name: str = "default") -> dict:
        """
        Start a new flow run.
        Creates a FlowRun in DB and begins execution.
        Returns final result dict.
        """
        from AINDY.db.models.flow_run import FlowRun

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
            job_log_id=self.job_log_id,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            _tenant_id = str(self.user_id) if self.user_id else ""
            _eu = ExecutionUnitService(self.db).create(
                eu_type="flow",
                user_id=self.user_id,
                source_type="flow_run",
                source_id=run.id,
                flow_run_id=run.id,
                status="executing",
                extra={
                    "flow_name": flow_name,
                    "workflow_type": self.workflow_type,
                    "tenant_id": _tenant_id,
                    "priority": self.priority,
                },
            )
            # ── Fail-fast: EU must be valid before execution starts ───────────
            # create() returns None on any DB/constraint failure.  A None eu_id
            # means WAIT states can never be resumed and resource tracking is
            # broken.  Raise immediately so the FlowRun is marked failed at the
            # source, rather than silently proceeding to discover the gap later
            # (e.g. at WAIT time when the damage is already done).
            if _eu is None:
                raise RuntimeError(
                    f"ExecutionUnit creation returned None for "
                    f"flow_run={run.id!r} flow={flow_name!r} — "
                    f"execution cannot start without a valid EU. "
                    f"Check DB connectivity and ExecutionUnit constraints."
                )
            self._eu_id = _eu.id
            self._tenant_id = _tenant_id
            # Register execution with ResourceManager (concurrency tracking)
            try:
                from AINDY.kernel.resource_manager import get_resource_manager
                get_resource_manager().mark_started(
                    _tenant_id, str(self._eu_id)
                )
            except Exception as _rm_exc:
                logger.debug("[EU] resource_manager.mark_started skipped: %s", _rm_exc)
        except RuntimeError:
            # Fail-fast errors must propagate — do not swallow with the
            # non-fatal handler below.  Mark the FlowRun as failed first.
            try:
                run.status = "failed"
                run.error_message = "ExecutionUnit creation failed — execution aborted"
                self.db.commit()
            except Exception:
                pass
            raise
        except Exception as _eu_exc:
            logger.warning("[EU] flow hook create failed — non-fatal | error=%s", _eu_exc)
            self._eu_id = None
            self._tenant_id = str(self.user_id) if self.user_id else ""
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
        root_event_id = emit_system_event(
            db=self.db,
            event_type=SystemEventTypes.EXECUTION_STARTED,
            user_id=self.user_id,
            trace_id=run.trace_id or str(run.id),
            parent_event_id=None,
            source="flow",
            payload={
                "run_id": str(run.id),
                "flow_name": flow_name,
                "workflow_type": self.workflow_type,
                "current_node": self.flow["start"],
            },
            required=True,
        )
        if isinstance(initial_state, dict) and root_event_id:
            initial_state["root_event_id"] = str(root_event_id)
            run.state = _json_safe(initial_state)
            self.db.commit()

        trace_token = set_trace_id(run.trace_id or str(run.id))
        parent_token = set_parent_event_id(str(root_event_id) if root_event_id else None)
        try:
            return self.resume(run.id)
        finally:
            reset_parent_event_id(parent_token)
            reset_trace_id(trace_token)

    def resume(self, run_id: str) -> dict:
        """
        Resume a flow run from its current node.
        """
        from AINDY.db.models.flow_run import FlowHistory, FlowRun

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

        # ── Distributed soft-lock: atomic status claim ────────────────────────
        # Applies only when the run is in 'waiting' state (rehydration resume
        # path).  start() creates FlowRuns with status='running' — those bypass
        # this guard entirely.
        #
        # The UPDATE is atomic at the DB level: exactly one instance wins the
        # race.  Any other instance that fires the same callback gets rowcount=0
        # and exits immediately, ensuring single-instance execution.
        if run.status == "waiting":
            claimed = (
                self.db.query(FlowRun)
                .filter(FlowRun.id == db_run_id, FlowRun.status == "waiting")
                .update({"status": "executing"}, synchronize_session=False)
            )
            try:
                self.db.commit()
            except Exception as _claim_exc:
                logger.warning(
                    "[Flow] resume claim commit failed for run=%s: %s",
                    db_run_id,
                    _claim_exc,
                )
                try:
                    self.db.rollback()
                except Exception:
                    pass
                return _format_execution_response(
                    status="SKIPPED",
                    trace_id=db_run_id,
                    result={
                        "skipped": True,
                        "reason": "claim commit failed — concurrent resume likely",
                    },
                    events=[],
                    next_action=None,
                    run_id=db_run_id,
                )

            if claimed == 0:
                logger.info(
                    "[Flow] resume skipped: run=%s already claimed by another instance",
                    db_run_id,
                )
                return _format_execution_response(
                    status="SKIPPED",
                    trace_id=db_run_id,
                    result={"skipped": True, "reason": "already claimed by another instance"},
                    events=[],
                    next_action=None,
                    run_id=db_run_id,
                )

            # Sync in-memory object — synchronize_session=False leaves run.status stale
            run.status = "executing"

        state = run.state or {}
        if isinstance(state, dict) and not state.get("trace_id"):
            state["trace_id"] = run.trace_id or get_trace_id() or str(run.id)
            run.state = _json_safe(state)
            if not run.trace_id:
                run.trace_id = state["trace_id"]
            self.db.commit()

        root_event_id = state.get("root_event_id") if isinstance(state, dict) else None
        current_node = run.current_node
        trace_token = set_trace_id(
            run.trace_id or (state.get("trace_id") if isinstance(state, dict) else str(run.id))
        )
        parent_token = set_parent_event_id(root_event_id)
        context = {
            "run_id": run.id,
            "trace_id": run.trace_id or (state.get("trace_id") if isinstance(state, dict) else None),
            "user_id": self.user_id,
            "workflow_type": self.workflow_type,
            "flow_name": run.flow_name,
            "attempts": {},
            "db": self.db,
        }

        def _fail_execution(error_message: str, *, failed_node: str, parent_event_id: str | None = None) -> dict:
            run.status = "failed"
            run.error_message = error_message
            run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            try:
                from AINDY.core.execution_unit_service import ExecutionUnitService
                _eus = ExecutionUnitService(self.db)
                _eu_id = getattr(self, "_eu_id", None)
                if _eu_id:
                    _eus.update_status(_eu_id, "failed")
                else:
                    _eu = _eus.get_by_source("flow_run", run.id)
                    if _eu:
                        _eus.update_status(_eu.id, "failed")
                # OS Layer: release concurrency slot
                try:
                    from AINDY.kernel.resource_manager import get_resource_manager as _get_rm_f
                    _get_rm_f().mark_completed(
                        getattr(self, "_tenant_id", str(self.user_id or "")),
                        str(_eu_id) if _eu_id else None,
                    )
                except Exception as _rm_fail_exc:
                    logger.debug("[EU] resource_manager.mark_completed(failed) skipped: %s", _rm_fail_exc)
            except Exception as _eu_exc:
                logger.warning("[EU] flow fail hook — non-fatal | error=%s", _eu_exc)
            try:
                _emit_execution_failed({
                    "db": self.db,
                    "run_id": str(run.id),
                    "trace_id": run.trace_id or str(run.id),
                    "user_id": str(self.user_id) if self.user_id else None,
                    "workflow_type": self.workflow_type,
                    "flow_name": run.flow_name,
                    "error": error_message,
                    "failed_node": failed_node,
                    "success": False,
                })
            except Exception as exc:
                logger.warning("Execution failure hook skipped: %s", exc)
            emit_system_event(
                db=self.db,
                event_type=SystemEventTypes.EXECUTION_FAILED,
                user_id=self.user_id,
                trace_id=run.trace_id or str(run.id),
                parent_event_id=root_event_id,
                source="flow",
                payload={
                    "run_id": str(run.id),
                    "workflow_type": self.workflow_type,
                    "failed_node": failed_node,
                    "error": error_message,
                },
                required=True,
            )
            emit_error_event(
                db=self.db,
                error_type="execution",
                message=error_message,
                user_id=self.user_id,
                trace_id=run.trace_id or str(run.id),
                parent_event_id=parent_event_id,
                source="flow",
                payload={
                    "run_id": str(run.id),
                    "workflow_type": self.workflow_type,
                    "failed_node": failed_node,
                },
                required=True,
            )
            return _format_execution_response(
                status="FAILED",
                trace_id=run.trace_id or str(run.id),
                result={"error": error_message, "failed_node": failed_node},
                events=_serialize_flow_events(self.db, run.id),
                next_action=None,
                run_id=run.id,
                state=state,
            )

        try:
            while True:
                input_snapshot = dict(state)
                node_started_event_id = queue_system_event(
                    db=self.db,
                    event_type=SystemEventTypes.FLOW_NODE_STARTED,
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    parent_event_id=root_event_id,
                    source="flow",
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "node": current_node,
                    },
                    required=True,
                )
                node_parent_token = set_parent_event_id(str(node_started_event_id) if node_started_event_id else root_event_id)
                # ── OS Layer: resource quota pre-check ────────────────────────
                try:
                    from AINDY.kernel.resource_manager import get_resource_manager as _get_rm
                    _rm = _get_rm()
                    _tenant_id = getattr(self, "_tenant_id", str(self.user_id or ""))
                    _eu_id_str = str(getattr(self, "_eu_id", "") or "")
                    _can_run, _run_reason = _rm.can_execute(_tenant_id, _eu_id_str)
                    if not _can_run:
                        # Pause run — re-queue via SchedulerEngine
                        run.status = "waiting"
                        run.waiting_for = "resource_available"
                        run.current_node = current_node
                        run.state = _json_safe(state)
                        self.db.commit()
                        try:
                            from AINDY.kernel.scheduler_engine import get_scheduler_engine, ScheduledItem
                            from AINDY.core.wait_condition import WaitCondition
                            _se = get_scheduler_engine()
                            _this_run_id = str(run.id)
                            _this_runner = self
                            _rw_trace = str(run.trace_id or _this_run_id)
                            _se.register_wait(
                                run_id=_this_run_id,
                                wait_for_event="resource_available",
                                tenant_id=_tenant_id,
                                eu_id=_eu_id_str,
                                resume_callback=lambda: _this_runner.resume(_this_run_id),
                                priority=getattr(self, "priority", "normal"),
                                correlation_id=_rw_trace,
                                trace_id=_rw_trace,
                                eu_type="flow",
                                wait_condition=WaitCondition.for_event(
                                    "resource_available", correlation_id=_rw_trace
                                ),
                            )
                        except Exception as _se_exc:
                            logger.debug("[Flow] scheduler register_wait skipped: %s", _se_exc)
                        reset_parent_event_id(node_parent_token)
                        return _format_execution_response(
                            status="WAITING",
                            trace_id=run.trace_id or str(run.id),
                            result={"waiting_for": "resource_available", "reason": _run_reason},
                            events=_serialize_flow_events(self.db, run.id),
                            next_action=None,
                            run_id=run.id,
                            state=state,
                        )
                    # Mid-execution quota check (cpu_time, syscall_count)
                    _quota_ok, _quota_reason = _rm.check_quota(_eu_id_str)
                    if not _quota_ok:
                        reset_parent_event_id(node_parent_token)
                        return _fail_execution(
                            _quota_reason,
                            failed_node=current_node,
                            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                        )
                except (ImportError, AttributeError) as _rm_import_exc:
                    logger.debug("[Flow] resource check skipped: %s", _rm_import_exc)
                # ─────────────────────────────────────────────────────────────
                _node_t_start = time.monotonic()
                try:
                    result = execute_node(current_node, state, context)
                except PermissionError as exc:
                    queue_system_event(
                        db=self.db,
                        event_type=SystemEventTypes.FLOW_NODE_FAILED,
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        parent_event_id=node_started_event_id,
                        source="flow",
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "node": current_node,
                            "error": str(exc),
                        },
                        required=True,
                    )
                    return _fail_execution(str(exc), failed_node=current_node, parent_event_id=str(node_started_event_id) if node_started_event_id else None)
                except Exception as exc:
                    logger.error("Node %s raised exception: %s", current_node, exc)
                    queue_system_event(
                        db=self.db,
                        event_type=SystemEventTypes.FLOW_NODE_FAILED,
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        parent_event_id=node_started_event_id,
                        source="flow",
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "node": current_node,
                            "error": str(exc),
                        },
                        required=True,
                    )
                    return _fail_execution(str(exc), failed_node=current_node, parent_event_id=str(node_started_event_id) if node_started_event_id else None)
                finally:
                    reset_parent_event_id(node_parent_token)

                node_status = result["status"]
                patch = result.get("output_patch", {})
                exec_ms = result.get("_execution_time_ms", 0) or int((time.monotonic() - _node_t_start) * 1000)
                # ── OS Layer: record node resource usage ──────────────────────
                try:
                    from AINDY.kernel.resource_manager import get_resource_manager as _get_rm2
                    _eu_id_str2 = str(getattr(self, "_eu_id", "") or "")
                    if _eu_id_str2:
                        _get_rm2().record_usage(
                            _eu_id_str2,
                            {"cpu_time_ms": exec_ms, "syscall_count": 0},
                        )
                except Exception as _rm_rec_exc:
                    logger.debug("[Flow] resource record skipped: %s", _rm_rec_exc)
                # ─────────────────────────────────────────────────────────────
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

                queue_system_event(
                    db=self.db,
                    event_type=SystemEventTypes.FLOW_NODE_COMPLETED if node_status in {"SUCCESS", "WAIT"} else SystemEventTypes.FLOW_NODE_FAILED,
                    user_id=self.user_id,
                    trace_id=run.trace_id or str(run.id),
                    parent_event_id=node_started_event_id,
                    source="flow",
                    payload={
                        "run_id": str(run.id),
                        "workflow_type": self.workflow_type,
                        "node": current_node,
                        "status": node_status,
                        "execution_time_ms": exec_ms,
                        "error": result.get("error"),
                    },
                    required=True,
                )

                if node_status == "SUCCESS":
                    state.update(patch)
                elif node_status == "RETRY":
                    attempts = context["attempts"].get(current_node, 0)
                    # Per-node override: flow dicts may carry node_configs["<node>"]["max_retries"].
                    # resolve_retry_policy(node_max_retries=...) returns a policy with that limit;
                    # when None it falls back to _FLOW_RETRY_POLICY (module default = 3).
                    _node_cfg = self.flow.get("node_configs", {}).get(current_node, {})
                    _run_policy = _resolve_retry_policy(
                        execution_type="flow",
                        node_max_retries=_node_cfg.get("max_retries"),
                    )
                    if attempts < _run_policy.max_attempts:
                        logger.warning("Node %s retrying (attempt %d)", current_node, attempts)
                        continue
                    return _fail_execution(
                        f"Node {current_node} failed after {attempts} retries",
                        failed_node=current_node,
                        parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                    )
                elif node_status == "FAILURE":
                    return _fail_execution(
                        result.get("error", f"Node {current_node} failed"),
                        failed_node=current_node,
                        parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                    )
                elif node_status == "WAIT":
                    wait_for = result.get("wait_for")
                    if not wait_for:
                        return _fail_execution(
                            f"Node {current_node} returned WAIT without wait_for",
                            failed_node=current_node,
                            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                        )
                    run.status = "waiting"
                    run.waiting_for = wait_for
                    run.state = _json_safe(state)
                    run.current_node = current_node
                    self.db.commit()
                    # Register with SchedulerEngine — single WAIT authority.
                    # resume_callback re-enters PersistentFlowRunner.resume() so
                    # the resumed run re-uses the same flow checkpoint.
                    try:
                        from AINDY.kernel.scheduler_engine import get_scheduler_engine
                        from AINDY.core.wait_condition import WaitCondition
                        _nw_run_id = str(run.id)
                        _nw_runner = self
                        _nw_trace = str(run.trace_id or _nw_run_id)
                        get_scheduler_engine().register_wait(
                            run_id=_nw_run_id,
                            wait_for_event=wait_for,
                            tenant_id=str(self.user_id or ""),
                            eu_id=str(getattr(self, "_eu_id", "") or ""),
                            resume_callback=lambda: _nw_runner.resume(_nw_run_id),
                            priority=getattr(self, "priority", "normal"),
                            correlation_id=_nw_trace,
                            trace_id=_nw_trace,
                            eu_type="flow",
                            wait_condition=WaitCondition.for_event(
                                wait_for, correlation_id=_nw_trace
                            ),
                        )
                    except Exception as _nw_exc:
                        logger.debug("[Flow] node-WAIT scheduler register_wait skipped: %s", _nw_exc)
                    queue_system_event(
                        db=self.db,
                        event_type=SystemEventTypes.FLOW_WAITING,
                        user_id=self.user_id,
                        trace_id=run.trace_id or str(run.id),
                        parent_event_id=node_started_event_id,
                        source="flow",
                        payload={
                            "run_id": str(run.id),
                            "workflow_type": self.workflow_type,
                            "node": current_node,
                            "waiting_for": wait_for,
                        },
                        required=True,
                    )
                    return _format_execution_response(
                        status="WAITING",
                        trace_id=run.trace_id or str(run.id),
                        result={"waiting_for": wait_for},
                        events=_serialize_flow_events(self.db, run.id),
                        next_action=None,
                        run_id=run.id,
                        state=state,
                    )

                if current_node in self.flow.get("end", []):
                    try:
                        execution_result = _extract_execution_result(self.workflow_type, state)
                        handoff = _extract_async_handoff(execution_result)
                        if handoff is not None:
                            update_count = (
                                self.db.query(type(run))
                                .filter(type(run).id == run.id)
                                .update(
                                    {
                                        type(run).status: handoff["status"].lower(),
                                        type(run).state: _json_safe(state),
                                        type(run).current_node: current_node,
                                        type(run).waiting_for: None,
                                        type(run).job_log_id: handoff["job_log_id"] or run.job_log_id,
                                    },
                                    synchronize_session=False,
                                )
                            )
                            if update_count != 1:
                                return _fail_execution(
                                    f"FlowRun {run.id} not found during async handoff finalization",
                                    failed_node=current_node,
                                    parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                                )
                            run_id = run.id
                            self.db.commit()
                            try:
                                self.db.expunge(run)
                            except Exception:
                                pass
                            self.db.expire_all()
                            queued_run = (
                                self.db.query(type(run))
                                .filter(type(run).id == run_id)
                                .first()
                            )
                            return _format_execution_response(
                                status=handoff["status"],
                                trace_id=queued_run.trace_id or str(queued_run.id),
                                result=execution_result,
                                events=_serialize_flow_events(self.db, queued_run.id),
                                next_action=_extract_next_action(execution_result),
                                run_id=queued_run.id,
                                state=state,
                            )

                        self._capture_flow_completion(run, state)
                        run.status = "success"
                        run.state = _json_safe(state)
                        run.completed_at = datetime.now(timezone.utc)
                        self.db.commit()
                        try:
                            _emit_execution_completed({
                                "db": self.db,
                                "run_id": str(run.id),
                                "trace_id": run.trace_id or str(run.id),
                                "user_id": str(self.user_id) if self.user_id else None,
                                "workflow_type": self.workflow_type,
                                "flow_name": run.flow_name,
                                "execution_result": execution_result,
                                "success": True,
                            })
                        except Exception as exc:
                            logger.warning("Execution completion hook skipped: %s", exc)
                        emit_system_event(
                            db=self.db,
                            event_type=SystemEventTypes.EXECUTION_COMPLETED,
                            user_id=self.user_id,
                            trace_id=run.trace_id or str(run.id),
                            parent_event_id=root_event_id,
                            source="flow",
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
                        return _fail_execution(
                            f"Completion finalization failed: {exc}",
                            failed_node=current_node,
                            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                        )

                next_node = resolve_next_node(current_node, state, self.flow)
                if not next_node:
                    return _fail_execution(
                        f"No next node from {current_node} - flow graph incomplete",
                        failed_node=current_node,
                        parent_event_id=str(node_started_event_id) if node_started_event_id else None,
                    )

                run.current_node = next_node
                run.state = _json_safe(state)
                self.db.commit()
                current_node = next_node
        finally:
            reset_parent_event_id(parent_token)
            reset_trace_id(trace_token)

    # Phase D: FlowHistory → Memory Bridge ───────────────────────────────────

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
            from AINDY.db.models.flow_run import FlowHistory

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

            from AINDY.platform_layer.registry import get_flow_completion_event

            event_type = get_flow_completion_event(self.workflow_type) or "flow_completion"
            namespace = self.workflow_type.split("_")[0]

            queue_memory_capture(
                db=self.db,
                user_id=self.user_id,
                agent_namespace=namespace,
                event_type=event_type,
                content=content,
                source=f"flow_history:{run.flow_name}",
                tags=["flow_history", "execution_pattern", self.workflow_type],
                context={"run_id": run.id, "total_ms": total_ms},
            )
            try:
                from AINDY.core.execution_unit_service import ExecutionUnitService
                _eus = ExecutionUnitService(self.db)
                _eu_id = getattr(self, "_eu_id", None)
                if _eu_id:
                    _eus.update_status(_eu_id, "completed")
                else:
                    _eu = _eus.get_by_source("flow_run", run.id)
                    if _eu:
                        _eus.update_status(_eu.id, "completed")
                # OS Layer: release concurrency slot
                try:
                    from AINDY.kernel.resource_manager import get_resource_manager as _get_rm_s
                    _get_rm_s().mark_completed(
                        getattr(self, "_tenant_id", str(self.user_id or "")),
                        str(_eu_id) if _eu_id else None,
                    )
                except Exception as _rm_succ_exc:
                    logger.debug("[EU] resource_manager.mark_completed(success) skipped: %s", _rm_succ_exc)
            except Exception as _eu_exc:
                logger.warning("[EU] flow completion hook — non-fatal | error=%s", _eu_exc)
        except Exception as e:
            logger.warning("FlowHistory -> Memory Bridge capture failed: %s", e)
            emit_error_event(
                db=self.db,
                error_type="memory_capture",
                message=str(e),
                user_id=self.user_id,
                trace_id=get_trace_id() or getattr(run, "trace_id", None),
                parent_event_id=state.get("root_event_id") if isinstance(state, dict) else None,
                source="flow",
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
    Deliver an external event to waiting flow runs and hand resume authority
    to SchedulerEngine.

    This function has exactly two responsibilities and nothing more:

    1. **Event payload delivery** (state preparation only):
       Inject ``payload`` into each waiting FlowRun's ``state["event"]`` so
       that Nodus ``event.wait()`` can retrieve it on re-execution.
       No status fields are mutated; no resume is triggered here.

    2. **Resume delegation**:
       Call ``SchedulerEngine.notify_event(event_type)`` which matches
       registered ``_waiting`` entries by ``wait_condition.event_name``,
       applies correlation-id filtering, and re-enqueues matched runs
       through ``ExecutionDispatcher``.

    All resume authority — matching, ordering, dispatching, duplicate
    prevention — belongs exclusively to SchedulerEngine.  The old pattern
    of ``run.status = "running"`` / ``runner.resume()`` is removed.

    Args:
        event_type:  The event type to deliver (e.g. ``"approval.received"``).
        payload:     Arbitrary event payload forwarded into FlowRun state.
        db:          Active SQLAlchemy session for state write.
        user_id:     Retained for API compatibility — no longer used for
                     payload-injection filtering.  Scope is now derived from
                     the scheduler's correlation_id match (same predicate as
                     ``notify_event()``), which guarantees that every run
                     receiving a payload is also a run that will be resumed.

    Returns:
        List of per-run payload acknowledgements ``{run_id, payload_injected}``.
        The caller receives an ack per run that got the state update; the actual
        resume count is determined by the scheduler.
    """
    from AINDY.db.models.flow_run import FlowRun
    from AINDY.kernel.scheduler_engine import get_scheduler_engine

    scheduler = get_scheduler_engine()
    corr = (payload or {}).get("correlation_id") or None

    # ── 1. Event payload delivery ─────────────────────────────────────────────
    # Scope: ask the scheduler which run_ids it *will* resume for this event.
    # Inject payload into exactly those FlowRun rows — no more, no less.
    # This aligns injection scope with resume scope so Nodus event.wait()
    # always receives its payload on re-execution.
    #
    # peek_matching_run_ids() is a read-only scan (no entries deleted/enqueued)
    # and MUST be called before notify_event() because notify_event() removes
    # matched entries from _waiting.
    #
    # Status fields are intentionally NOT mutated here — the flow runner handles
    # its own checkpoint transitions on resume.
    results: list[dict] = []

    matching_run_ids = scheduler.peek_matching_run_ids(event_type, correlation_id=corr)
    if not matching_run_ids:
        logger.debug(
            "[route_event] no waiting runs matched event=%s corr=%s — skipping injection",
            event_type, corr,
        )
        # Fall through to step 2 (notify_event) — let scheduler confirm and log.
        query_runs = []
    else:
        query_runs = db.query(FlowRun).filter(
            FlowRun.id.in_(matching_run_ids),
            FlowRun.status == "waiting",
        ).all()

    for run in query_runs:
        try:
            state = dict(run.state or {})
            state["event"] = payload
            run.state = _json_safe(state)
            db.flush()
            results.append({"run_id": str(run.id), "payload_injected": True})
            logger.debug(
                "[route_event] payload injected run=%s event=%s", run.id, event_type
            )
        except Exception as _inj_exc:
            logger.warning(
                "[route_event] payload inject failed run=%s: %s", run.id, _inj_exc
            )

    try:
        db.commit()
    except Exception as _commit_exc:
        logger.warning(
            "[route_event] state commit failed event=%s: %s", event_type, _commit_exc
        )

    # ── 2. Resume delegation ──────────────────────────────────────────────────
    # publish_event() is the single entry point for all event emission.
    # It runs the local notify_event() scan on this instance AND publishes to
    # the Redis event bus so all other instances wake their own registered
    # waiters.  No runner.resume() calls, no FLOW_REGISTRY lookups, no status
    # mutations here — the scheduler and its callbacks handle all of that.
    try:
        from AINDY.kernel.event_bus import publish_event
        resumed = publish_event(event_type, correlation_id=corr)
        logger.info(
            "[route_event] publish_event resumed=%d event=%s corr=%s",
            resumed, event_type, corr,
        )
    except Exception as _sched_exc:
        logger.warning(
            "[route_event] publish_event failed event=%s: %s", event_type, _sched_exc
        )

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
    Used by Flow Plan Selection to learn which flows work best.
    """
    if not db:
        return

    from AINDY.db.models.flow_run import EventOutcome

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


# ── Flow Plan Selection ─────────────────────────────────────────────────────────


# Intent Pipeline ────────────────────────────────────────────────────────────


def generate_plan_from_intent(intent: dict) -> dict:
    """
    Generate a basic execution plan from intent data.
    Used when no registered flow plan exists for this intent type.
    Fallback: linear plan of steps.
    """
    from AINDY.platform_layer.registry import get_flow_plan

    workflow_type = intent.get("workflow_type", "generic")
    return get_flow_plan(workflow_type) or get_flow_plan("generic") or {"steps": ["execute", "store_result"]}


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


def _execute_intent_direct(
    intent_data: dict,
    db: Session,
    user_id: str = None,
) -> dict:
    """
    Internal execute_intent implementation.

    Called by the sys.v1.flow.execute_intent syscall handler and by
    execute_intent() when user_id is absent (anonymous/system calls).
    Do not call directly from new code — use execute_intent() or dispatch
    sys.v1.flow.execute_intent through the SyscallDispatcher.
    """
    intent_type = intent_data.get("workflow_type", "generic")

    flow = _registry_flow_plan(intent_type, db, user_id)

    # Fall back to generated plan
    if not flow:
        plan = generate_plan_from_intent(intent_data)
        flow = compile_plan_to_flow(plan)
        flow_name = f"generated_{intent_type}"
    else:
        flow_name = f"registered_{intent_type}"

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


def execute_intent(
    intent_data: dict,
    db: Session,
    user_id: str = None,
) -> dict:
    """
    Top-level intent execution — routes through sys.v1.flow.execute_intent.

    1. Try Flow Plan Selection (learned flow)
    2. Fall back to generated plan
    3. Execute via PersistentFlowRunner

    Routes through SyscallDispatcher when user_id is present, giving unified
    capability enforcement, quota tracking, and observability. Falls back to
    _execute_intent_direct() for anonymous/system calls (user_id=None).
    """
    if not user_id:
        logger.debug(
            "[execute_intent] no user_id — executing directly "
            "(syscall layer requires identity)"
        )
        return _execute_intent_direct(intent_data, db, user_id)

    import uuid as _uuid
    from AINDY.kernel.syscall_dispatcher import _EU_ID_CTX, _TRACE_ID_CTX, get_dispatcher, SyscallContext

    # Reuse parent trace/EU when running inside an existing syscall chain;
    # otherwise start a fresh root trace for this intent execution.
    trace_id = _TRACE_ID_CTX.get() or str(_uuid.uuid4())
    eu_id = _EU_ID_CTX.get() or trace_id
    ctx = SyscallContext(
        execution_unit_id=eu_id,
        user_id=str(user_id),
        capabilities=["flow.run", "flow.execute"],
        trace_id=trace_id,
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.flow.execute_intent",
        {"intent_data": intent_data},
        ctx,
    )
    if result["status"] == "error":
        raise RuntimeError(
            f"sys.v1.flow.execute_intent failed: {result.get('error', '')}"
        )
    return result["data"]["intent_result"]


# ── Router-facing entry point ──────────────────────────────────────────────────


def _run_flow_direct(
    flow_name: str, state: dict, db: Session = None, user_id: str = None
) -> dict:
    """
    Internal run_flow implementation.

    Called by the sys.v1.flow.run syscall handler and by run_flow() when
    user_id is absent. Do not call directly from new code — use run_flow()
    or dispatch sys.v1.flow.run through the SyscallDispatcher.
    """
    flow = FLOW_REGISTRY.get(flow_name)
    if not flow:
        raise KeyError(
            f"Flow '{flow_name}' not registered. "
            f"Available: {sorted(FLOW_REGISTRY.keys())}"
        )
    normalized_user_id = normalize_uuid(user_id) if user_id is not None else None
    runner = PersistentFlowRunner(
        flow=flow,
        db=db,
        user_id=normalized_user_id,
        workflow_type=flow_name,
    )
    return runner.start(initial_state=dict(state), flow_name=flow_name)


def run_flow(flow_name: str, state: dict, db: Session = None, user_id: str = None) -> dict:
    """
    Execute a registered flow by name.

    Routes through sys.v1.flow.run for unified capability enforcement, quota
    tracking, and observability. Raises KeyError if the flow is not registered.

    When user_id is None (anonymous/system calls), falls through to
    _run_flow_direct() because the syscall layer requires tenant identity.

    Returns the standard execution envelope:
        {
            "status": "success" | "error",
            "data":   <execution result>,
            "trace_id": str,
            "run_id":   str,
            ...
        }

    Usage inside a handler:
        result = run_flow("example_flow", {"input": "..."}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError(result.get("data", {}).get("message", "flow failed"))
        return result.get("data")
    """
    if not user_id:
        logger.debug(
            "[run_flow] no user_id — executing '%s' directly "
            "(syscall layer requires identity)",
            flow_name,
        )
        return _run_flow_direct(flow_name, state or {}, db, user_id)

    import uuid as _uuid
    from AINDY.kernel.syscall_dispatcher import _EU_ID_CTX, _TRACE_ID_CTX, get_dispatcher, SyscallContext

    # Reuse parent trace/EU when running inside an existing syscall chain;
    # otherwise start a fresh root trace for this flow run.
    trace_id = _TRACE_ID_CTX.get() or str(_uuid.uuid4())
    eu_id = _EU_ID_CTX.get() or trace_id
    ctx = SyscallContext(
        execution_unit_id=eu_id,
        user_id=str(user_id),
        capabilities=["flow.run"],
        trace_id=trace_id,
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.flow.run",
        {"flow_name": flow_name, "initial_state": state or {}, "workflow_type": flow_name},
        ctx,
    )
    if result["status"] == "error":
        error_msg = result.get("error", "")
        # Preserve original KeyError for unknown/unregistered flows.
        if "not registered" in error_msg or "unknown flow" in error_msg.lower():
            raise KeyError(error_msg)
        raise RuntimeError(f"sys.v1.flow.run failed: {error_msg}")
    return result["data"]["flow_result"]




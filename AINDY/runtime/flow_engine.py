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
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session
from core.execution_envelope import error as execution_error
from core.execution_envelope import success as execution_success
from domain.goal_service import update_goals_from_execution
from core.execution_signal_helper import queue_memory_capture, queue_system_event
emit_system_event = queue_system_event
from core.system_event_service import emit_error_event
from core.system_event_types import SystemEventTypes
from utils.trace_context import ensure_trace_id
from utils.trace_context import get_trace_id
from utils.trace_context import reset_parent_event_id
from utils.trace_context import reset_trace_id
from utils.trace_context import set_parent_event_id
from utils.trace_context import set_trace_id
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
        # Flows added in unified execution model migration
        "arm_generate": "generation_result",
        "leadgen_search": "search_results",
        "task_create": "task_create_result",
        "task_start": "task_start_result",
        "task_pause": "task_pause_result",
        "goal_create": "goal_create_result",
        "score_recalculate": "score_recalculate_result",
        "score_feedback": "score_feedback_result",
        # ── Hard Execution Boundary flows ──────────────────────────────────────
        "arm_logs": "arm_logs_result",
        "arm_config_get": "arm_config_get_result",
        "arm_config_update": "arm_config_update_result",
        "arm_metrics": "arm_metrics_result",
        "arm_config_suggest": "arm_config_suggest_result",
        "goals_list": "goals_list_result",
        "goals_state": "goals_state_result",
        "score_get": "score_get_result",
        "score_history": "score_history_result",
        "score_feedback_list": "score_feedback_list_result",
        "leadgen_list": "leadgen_list_result",
        "leadgen_preview_search": "leadgen_preview_search_result",
        "tasks_list": "tasks_list_result",
        "tasks_recurrence_check": "tasks_recurrence_check_result",
        "agent_run_create": "agent_run_create_result",
        "agent_runs_list": "agent_runs_list_result",
        "agent_run_get": "agent_run_get_result",
        "agent_run_approve": "agent_run_approve_result",
        "agent_run_reject": "agent_run_reject_result",
        "agent_run_recover": "agent_run_recover_result",
        "agent_run_replay": "agent_run_replay_result",
        "agent_run_steps": "agent_run_steps_result",
        "agent_run_events": "agent_run_events_result",
        "agent_tools_list": "agent_tools_list_result",
        "agent_trust_get": "agent_trust_get_result",
        "agent_trust_update": "agent_trust_update_result",
        "agent_suggestions_get": "agent_suggestions_get_result",
        "analytics_linkedin_ingest": "analytics_linkedin_ingest_result",
        "analytics_masterplan_get": "analytics_masterplan_get_result",
        "analytics_masterplan_summary": "analytics_masterplan_summary_result",
        "watcher_signals_receive": "watcher_ingest_result",
        "watcher_signals_list": "watcher_signals_list_result",
        "genesis_session_create": "genesis_session_create_result",
        "genesis_session_get": "genesis_session_get_result",
        "genesis_draft_get": "genesis_draft_get_result",
        "genesis_synthesize": "genesis_synthesize_result",
        "genesis_audit": "genesis_audit_result",
        "genesis_lock": "genesis_lock_result",
        "genesis_activate": "genesis_activate_result",
        "flow_runs_list": "flow_runs_list_result",
        "flow_run_get": "flow_run_get_result",
        "flow_run_history": "flow_run_history_result",
        "flow_run_resume": "flow_run_resume_result",
        "flow_registry_get": "flow_registry_get_result",
        "memory_node_create": "memory_node_create_result",
        "memory_node_get": "memory_node_get_result",
        "memory_node_update": "memory_node_update_result",
        "memory_node_history": "memory_node_history_result",
        "memory_node_links": "memory_node_links_result",
        "memory_nodes_search_tags": "memory_nodes_search_tags_result",
        "memory_link_create": "memory_link_create_result",
        "memory_node_traverse": "memory_node_traverse_result",
        "memory_nodes_expand": "memory_nodes_expand_result",
        "memory_nodes_search_similar": "memory_nodes_search_similar_result",
        "memory_recall": "memory_recall_result",
        "memory_recall_v3": "memory_recall_v3_result",
        "memory_recall_federated": "memory_recall_federated_result",
        "memory_agents_list": "memory_agents_list_result",
        "memory_node_share": "memory_node_share_result",
        "memory_agent_recall": "memory_agent_recall_result",
        "memory_node_feedback": "memory_node_feedback_result",
        "memory_node_performance": "memory_node_performance_result",
        "memory_suggest": "memory_suggest_result",
        "memory_nodus_execute": "memory_nodus_execute_result",
        "memory_execute_loop": "memory_execution_response",
        "nodus_execute": "nodus_execute_result",
        # Automation
        "automation_logs_list": "automation_logs_list_result",
        "automation_log_get": "automation_log_get_result",
        "automation_log_replay": "automation_log_replay_result",
        "automation_scheduler_status": "automation_scheduler_status_result",
        "automation_task_trigger": "automation_task_trigger_result",
        # Freelance
        "freelance_order_create": "freelance_order_create_result",
        "freelance_order_deliver": "freelance_order_deliver_result",
        "freelance_delivery_update": "freelance_delivery_update_result",
        "freelance_feedback_collect": "freelance_feedback_collect_result",
        "freelance_orders_list": "freelance_orders_list_result",
        "freelance_feedback_list": "freelance_feedback_list_result",
        "freelance_metrics_latest": "freelance_metrics_latest_result",
        "freelance_metrics_update": "freelance_metrics_update_result",
        "freelance_delivery_generate": "freelance_delivery_generate_result",
        # Research
        "research_create": "research_create_result",
        "research_list": "research_list_result",
        "research_query": "research_query_result",
        "search_history_list": "search_history_list_result",
        "search_history_get": "search_history_get_result",
        "search_history_delete": "search_history_delete_result",
        # Masterplan
        "masterplan_lock_from_genesis": "masterplan_lock_from_genesis_result",
        "masterplan_lock": "masterplan_lock_result",
        "masterplan_list": "masterplan_list_result",
        "masterplan_get": "masterplan_get_result",
        "masterplan_anchor": "masterplan_anchor_result",
        "masterplan_projection": "masterplan_projection_result",
        "masterplan_activate": "masterplan_activate_result",
        # Autonomy
        "autonomy_decisions_list": "autonomy_decisions_list_result",
        # Watcher autonomy gate
        "watcher_evaluate_trigger": "watcher_evaluate_trigger_result",
        # Dashboard
        "dashboard_overview": "dashboard_overview_result",
        "health_dashboard_list": "health_dashboard_list_result",
        # Observability
        "observability_scheduler_status": "observability_scheduler_status_result",
        "observability_requests": "observability_requests_result",
        "observability_dashboard": "observability_dashboard_result",
        "observability_rippletrace": "observability_rippletrace_result",
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

    automation_log_id = (
        nested_result.get("automation_log_id")
        or (data.get("automation_log_id") if isinstance(data, dict) else None)
        or response.get("automation_log_id")
    )

    return {
        "status": handoff_status,
        "response": response,
        "automation_log_id": automation_log_id,
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
    from core.execution_record_service import build_execution_record

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
from core.retry_policy import resolve_retry_policy as _resolve_retry_policy  # noqa: E402
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
    from memory.memory_helpers import enrich_context
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
    from memory.memory_helpers import record_execution_feedback
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
        automation_log_id: str = None,
        priority: str = "normal",
    ):
        self.flow = flow
        self.db = db
        self.user_id = normalize_uuid(user_id) if user_id is not None else None
        self.workflow_type = workflow_type
        self.automation_log_id = automation_log_id
        self.priority = priority

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
        try:
            from core.execution_unit_service import ExecutionUnitService
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
            self._eu_id = _eu.id if _eu else None
            self._tenant_id = _tenant_id
            # Register execution with ResourceManager (concurrency tracking)
            try:
                from kernel.resource_manager import get_resource_manager
                get_resource_manager().mark_started(
                    _tenant_id, str(self._eu_id) if self._eu_id else None
                )
            except Exception as _rm_exc:
                logger.debug("[EU] resource_manager.mark_started skipped: %s", _rm_exc)
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
                from core.execution_unit_service import ExecutionUnitService
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
                    from kernel.resource_manager import get_resource_manager as _get_rm_f
                    _get_rm_f().mark_completed(
                        getattr(self, "_tenant_id", str(self.user_id or "")),
                        str(_eu_id) if _eu_id else None,
                    )
                except Exception as _rm_fail_exc:
                    logger.debug("[EU] resource_manager.mark_completed(failed) skipped: %s", _rm_fail_exc)
            except Exception as _eu_exc:
                logger.warning("[EU] flow fail hook — non-fatal | error=%s", _eu_exc)
            try:
                update_goals_from_execution(
                    self.db,
                    user_id=str(self.user_id) if self.user_id else None,
                    workflow_type=self.workflow_type,
                    execution_result={"error": error_message, "failed_node": failed_node},
                    success=False,
                )
            except Exception as exc:
                logger.warning("Goal progress failure update skipped: %s", exc)
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
                    from kernel.resource_manager import get_resource_manager as _get_rm
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
                            from kernel.scheduler_engine import get_scheduler_engine, ScheduledItem
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
                    from kernel.resource_manager import get_resource_manager as _get_rm2
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
                        from kernel.scheduler_engine import get_scheduler_engine
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
                                        type(run).automation_log_id: handoff["automation_log_id"] or run.automation_log_id,
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
                            update_goals_from_execution(
                                self.db,
                                user_id=str(self.user_id) if self.user_id else None,
                                workflow_type=self.workflow_type,
                                execution_result=execution_result,
                                success=True,
                            )
                        except Exception as exc:
                            logger.warning("Goal progress success update skipped: %s", exc)
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
            from db.models.flow_run import FlowHistory

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
                from core.execution_unit_service import ExecutionUnitService
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
                    from kernel.resource_manager import get_resource_manager as _get_rm_s
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


# ── Router-facing entry point ──────────────────────────────────────────────────


def run_flow(flow_name: str, state: dict, db: Session, user_id: str = None) -> dict:
    """
    Execute a registered flow by name.

    Thin wrapper over PersistentFlowRunner for use inside router handlers.
    Raises KeyError immediately if the flow is not registered, so misconfigured
    routers fail loudly at startup rather than silently at request time.

    Returns the standard execution envelope:
        {
            "status": "success" | "error",
            "data":   <_extract_execution_result output>,
            "trace_id": str,
            "run_id":   str,
            ...
        }

    Usage inside a handler:
        result = run_flow("task_create", {"task_name": "..."}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError(result.get("data", {}).get("message", "flow failed"))
        return result.get("data")
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


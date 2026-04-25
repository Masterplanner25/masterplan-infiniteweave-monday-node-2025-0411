from AINDY.runtime.flow_engine.runner_completion import (
    capture_flow_completion,
)
from AINDY.runtime.flow_engine.runner_failure import fail_execution
from AINDY.runtime.flow_engine.runner_steps import (
    _advance_to_next_node,
    _check_resources,
    _claim_waiting_run,
    _execute_current_node,
    _handle_node_status,
    _queue_node_failure,
    _record_resource_usage,
)
from AINDY.runtime.flow_engine.serialization import (
    _format_execution_response,
    _json_safe,
)
from AINDY.runtime.flow_engine.shared import (
    Session,
    SystemEventTypes,
    emit_event,
    emit_system_event,
    ensure_trace_id,
    get_trace_id,
    logger,
    normalize_uuid,
    queue_system_event,
    reset_parent_event_id,
    reset_trace_id,
    set_parent_event_id,
    set_trace_id,
    uuid,
)


def _emit_execution_completed(context: dict):
    payload = {
        **context,
        "flow_id": context.get("run_id"),
        "status": "success",
        "context": context,
    }
    return emit_event(SystemEventTypes.EXECUTION_COMPLETED, payload)


def _emit_execution_failed(context: dict):
    payload = {
        **context,
        "flow_id": context.get("run_id"),
        "status": "failed",
        "context": context,
    }
    return emit_event(SystemEventTypes.EXECUTION_FAILED, payload)


class PersistentFlowRunner:
    _emit_execution_completed = staticmethod(_emit_execution_completed)
    _emit_execution_failed = staticmethod(_emit_execution_failed)
    _capture_flow_completion = capture_flow_completion
    _claim_waiting_run = _claim_waiting_run
    _execute_current_node = _execute_current_node
    _check_resources = _check_resources
    _queue_node_failure = _queue_node_failure
    _record_resource_usage = _record_resource_usage
    _handle_node_status = _handle_node_status
    _advance_to_next_node = _advance_to_next_node

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

    def _fail_execution(
        self,
        error_message: str,
        *,
        failed_node: str,
        parent_event_id: str | None = None,
    ):
        return fail_execution(
            self,
            self._current_run,
            self._current_state,
            self._root_event_id,
            error_message,
            failed_node=failed_node,
            parent_event_id=parent_event_id,
        )

    def start(self, initial_state: dict, flow_name: str = "default") -> dict:
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
        self._initialize_execution_unit(run, flow_name)

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
        from AINDY.runtime import flow_engine as flow_engine_module

        root_event_id = flow_engine_module.emit_system_event(
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

    def _initialize_execution_unit(self, run, flow_name: str) -> None:
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService

            tenant_id = str(self.user_id) if self.user_id else ""
            eu = ExecutionUnitService(self.db).create(
                eu_type="flow",
                user_id=self.user_id,
                source_type="flow_run",
                source_id=run.id,
                flow_run_id=run.id,
                status="executing",
                extra={
                    "flow_name": flow_name,
                    "workflow_type": self.workflow_type,
                    "tenant_id": tenant_id,
                    "priority": self.priority,
                },
            )
            if eu is None:
                raise RuntimeError(
                    f"ExecutionUnit creation returned None for flow_run={run.id!r} "
                    f"flow={flow_name!r} - execution cannot start without a valid EU. "
                    f"Check DB connectivity and ExecutionUnit constraints."
                )
            self._eu_id = eu.id
            self._tenant_id = tenant_id
            try:
                from AINDY.kernel.resource_manager import get_resource_manager

                get_resource_manager().mark_started(tenant_id, str(self._eu_id))
            except Exception as exc:
                logger.debug("[EU] resource_manager.mark_started skipped: %s", exc)
        except RuntimeError:
            try:
                run.status = "failed"
                run.error_message = "ExecutionUnit creation failed - execution aborted"
                self.db.commit()
            except Exception:
                pass
            raise
        except Exception as exc:
            logger.warning("[EU] flow hook create failed - non-fatal | error=%s", exc)
            self._eu_id = None
            self._tenant_id = str(self.user_id) if self.user_id else ""

    def resume(self, run_id: str) -> dict:
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

        claim_response = self._claim_waiting_run(run, db_run_id)
        if claim_response is not None:
            return claim_response

        def _reload_run() -> FlowRun | None:
            return self.db.query(FlowRun).filter(FlowRun.id == db_run_id).first()

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
            run.trace_id
            or (state.get("trace_id") if isinstance(state, dict) else str(run.id))
        )
        parent_token = set_parent_event_id(root_event_id)
        context = {
            "run_id": run.id,
            "trace_id": run.trace_id
            or (state.get("trace_id") if isinstance(state, dict) else None),
            "user_id": self.user_id,
            "workflow_type": self.workflow_type,
            "flow_name": run.flow_name,
            "attempts": {},
            "db": self.db,
        }
        self._current_run = run
        self._current_state = state
        self._root_event_id = root_event_id

        try:
            while True:
                run = _reload_run()
                if not run:
                    return _format_execution_response(
                        status="FAILED",
                        trace_id=db_run_id,
                        result={"error": f"FlowRun {db_run_id} disappeared during execution"},
                        events=[],
                        next_action=None,
                        run_id=db_run_id,
                    )
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

                execute_response = self._execute_current_node(
                    run,
                    state,
                    context,
                    current_node,
                    node_started_event_id,
                )
                if execute_response.get("final_response") is not None:
                    return execute_response["final_response"]

                run = _reload_run()
                if not run:
                    return _format_execution_response(
                        status="FAILED",
                        trace_id=db_run_id,
                        result={"error": f"FlowRun {db_run_id} disappeared after node execution"},
                        events=[],
                        next_action=None,
                        run_id=db_run_id,
                    )

                result = execute_response["result"]
                node_status = result["status"]
                patch = result.get("output_patch", {})
                exec_ms = result.get("_execution_time_ms", 0) or execute_response["exec_ms"]

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
                    event_type=(
                        SystemEventTypes.FLOW_NODE_COMPLETED
                        if node_status in {"SUCCESS", "WAIT"}
                        else SystemEventTypes.FLOW_NODE_FAILED
                    ),
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

                node_response = self._handle_node_status(
                    run,
                    state,
                    context,
                    current_node,
                    result,
                    patch,
                    node_status,
                    node_started_event_id,
                )
                if node_response == "retry":
                    continue
                if node_response is not None:
                    return node_response

                next_response = self._advance_to_next_node(
                    run,
                    state,
                    current_node,
                    node_started_event_id,
                )
                if isinstance(next_response, dict):
                    return next_response
                current_node = next_response
        finally:
            reset_parent_event_id(parent_token)
            reset_trace_id(trace_token)

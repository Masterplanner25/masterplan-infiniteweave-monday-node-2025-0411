from AINDY.runtime.flow_engine.node_executor import resolve_next_node
from AINDY.runtime.flow_engine.registry import FLOW_REGISTRY
from AINDY.runtime.flow_engine.runner_completion import maybe_finalize_completion
from AINDY.runtime.flow_engine.serialization import (
    _format_execution_response,
    _json_safe,
    _serialize_flow_events,
)
from AINDY.runtime.flow_engine.shared import (
    SystemEventTypes,
    _default_wait_deadline,
    _resolve_retry_policy,
    logger,
    queue_system_event,
    reset_parent_event_id,
    set_parent_event_id,
    time,
)


def _get_flow_wait_timeout(flow_name: str) -> int | None:
    flow_def = FLOW_REGISTRY.get(flow_name)
    if flow_def is None:
        return None
    return flow_def.get("wait_timeout_minutes")


def _claim_waiting_run(self, run, db_run_id: str):
    from AINDY.db.models.flow_run import FlowRun

    if run.status != "waiting":
        return None

    claimed = (
        self.db.query(FlowRun)
        .filter(FlowRun.id == db_run_id, FlowRun.status == "waiting")
        .update(
            {
                "status": "executing",
                "waiting_for": None,
                "wait_deadline": None,
            },
            synchronize_session=False,
        )
    )
    try:
        self.db.commit()
    except Exception as exc:
        logger.warning(
            "[Flow] resume claim commit failed for run=%s: %s",
            db_run_id,
            exc,
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
                "reason": "claim commit failed - concurrent resume likely",
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
            result={
                "skipped": True,
                "reason": "already claimed by another instance",
            },
            events=[],
            next_action=None,
            run_id=db_run_id,
        )
    run.status = "executing"
    return None


def _execute_current_node(
    self,
    run,
    state: dict,
    context: dict,
    current_node: str,
    node_started_event_id,
) -> dict:
    node_parent_token = set_parent_event_id(
        str(node_started_event_id) if node_started_event_id else self._root_event_id
    )
    try:
        resource_response = self._check_resources(
            run,
            state,
            current_node,
            node_started_event_id,
        )
        if resource_response is not None:
            return {"final_response": resource_response}

        node_t_start = time.monotonic()
        try:
            from AINDY.runtime import flow_engine as flow_engine_module

            result = flow_engine_module.execute_node(current_node, state, context)
        except PermissionError as exc:
            self._queue_node_failure(run, current_node, node_started_event_id, str(exc))
            return {
                "final_response": self._fail_execution(
                    str(exc),
                    failed_node=current_node,
                    parent_event_id=str(node_started_event_id)
                    if node_started_event_id
                    else None,
                )
            }
        except Exception as exc:
            logger.error("Node %s raised exception: %s", current_node, exc)
            self._queue_node_failure(run, current_node, node_started_event_id, str(exc))
            return {
                "final_response": self._fail_execution(
                    str(exc),
                    failed_node=current_node,
                    parent_event_id=str(node_started_event_id)
                    if node_started_event_id
                    else None,
                )
            }

        exec_ms = result.get("_execution_time_ms", 0) or int(
            (time.monotonic() - node_t_start) * 1000
        )
        self._record_resource_usage(exec_ms)
        return {"result": result, "exec_ms": exec_ms, "final_response": None}
    finally:
        reset_parent_event_id(node_parent_token)


def _check_resources(self, run, state: dict, current_node: str, node_started_event_id):
    try:
        from AINDY.kernel.resource_manager import get_resource_manager as get_rm

        rm = get_rm()
        tenant_id = getattr(self, "_tenant_id", str(self.user_id or ""))
        eu_id_str = str(getattr(self, "_eu_id", "") or "")
        can_run, run_reason = rm.can_execute(tenant_id, eu_id_str)
        if not can_run:
            run.status = "waiting"
            run.waiting_for = "resource_available"
            _timeout = _get_flow_wait_timeout(run.flow_name)
            run.wait_deadline = _default_wait_deadline(_timeout)
            run.current_node = current_node
            run.state = _json_safe(state)
            self.db.commit()
            try:
                from AINDY.core.wait_condition import WaitCondition
                from AINDY.kernel.scheduler_engine import get_scheduler_engine

                this_run_id = str(run.id)
                this_trace = str(run.trace_id or this_run_id)
                get_scheduler_engine().register_wait(
                    run_id=this_run_id,
                    wait_for_event="resource_available",
                    tenant_id=tenant_id,
                    eu_id=eu_id_str,
                    resume_callback=lambda: self.resume(this_run_id),
                    priority=getattr(self, "priority", "normal"),
                    correlation_id=this_trace,
                    trace_id=this_trace,
                    eu_type="flow",
                    wait_condition=WaitCondition.for_event(
                        "resource_available",
                        correlation_id=this_trace,
                    ),
                )
            except Exception as exc:
                logger.debug("[Flow] scheduler register_wait skipped: %s", exc)
            return _format_execution_response(
                status="WAITING",
                trace_id=run.trace_id or str(run.id),
                result={"waiting_for": "resource_available", "reason": run_reason},
                events=_serialize_flow_events(self.db, run.id),
                next_action=None,
                run_id=run.id,
                state=state,
            )

        quota_ok, quota_reason = rm.check_quota(eu_id_str)
        if not quota_ok:
            return self._fail_execution(
                quota_reason,
                failed_node=current_node,
                parent_event_id=str(node_started_event_id)
                if node_started_event_id
                else None,
            )
    except (ImportError, AttributeError) as exc:
        logger.debug("[Flow] resource check skipped: %s", exc)
    return None


def _queue_node_failure(self, run, current_node: str, node_started_event_id, error: str) -> None:
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
            "error": error,
        },
        required=True,
    )


def _record_resource_usage(self, exec_ms: int) -> None:
    try:
        from AINDY.kernel.resource_manager import get_resource_manager as get_rm

        eu_id_str = str(getattr(self, "_eu_id", "") or "")
        if eu_id_str:
            get_rm().record_usage(
                eu_id_str,
                {"cpu_time_ms": exec_ms, "syscall_count": 0},
            )
    except Exception as exc:
        logger.debug("[Flow] resource record skipped: %s", exc)


def _handle_node_status(
    self,
    run,
    state: dict,
    context: dict,
    current_node: str,
    result: dict,
    patch: dict,
    node_status: str,
    node_started_event_id,
):
    if node_status == "SUCCESS":
        state.update(patch)
    elif node_status == "RETRY":
        attempts = context["attempts"].get(current_node, 0)
        node_cfg = self.flow.get("node_configs", {}).get(current_node, {})
        run_policy = _resolve_retry_policy(
            execution_type="flow",
            node_max_retries=node_cfg.get("max_retries"),
        )
        if attempts < run_policy.max_attempts:
            logger.warning("Node %s retrying (attempt %d)", current_node, attempts)
            return "retry"
        return self._fail_execution(
            f"Node {current_node} failed after {attempts} retries",
            failed_node=current_node,
            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
        )
    elif node_status == "FAILURE":
        return self._fail_execution(
            result.get("error", f"Node {current_node} failed"),
            failed_node=current_node,
            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
        )
    elif node_status == "WAIT":
        wait_for = result.get("wait_for")
        if not wait_for:
            return self._fail_execution(
                f"Node {current_node} returned WAIT without wait_for",
                failed_node=current_node,
                parent_event_id=str(node_started_event_id) if node_started_event_id else None,
            )
        run.status = "waiting"
        run.waiting_for = wait_for
        _timeout = _get_flow_wait_timeout(run.flow_name)
        run.wait_deadline = _default_wait_deadline(_timeout)
        run.state = _json_safe(state)
        run.current_node = current_node
        self.db.commit()
        try:
            from AINDY.core.wait_condition import WaitCondition
            from AINDY.kernel.scheduler_engine import get_scheduler_engine

            wait_run_id = str(run.id)
            wait_trace = str(run.trace_id or wait_run_id)
            get_scheduler_engine().register_wait(
                run_id=wait_run_id,
                wait_for_event=wait_for,
                tenant_id=str(self.user_id or ""),
                eu_id=str(getattr(self, "_eu_id", "") or ""),
                resume_callback=lambda: self.resume(wait_run_id),
                priority=getattr(self, "priority", "normal"),
                correlation_id=wait_trace,
                trace_id=wait_trace,
                eu_type="flow",
                wait_condition=WaitCondition.for_event(
                    wait_for,
                    correlation_id=wait_trace,
                ),
            )
        except Exception as exc:
            logger.debug("[Flow] node-WAIT scheduler register_wait skipped: %s", exc)
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

    return maybe_finalize_completion(
        self,
        run,
        state,
        current_node,
        self._root_event_id,
        node_started_event_id,
    )


def _advance_to_next_node(
    self,
    run,
    state: dict,
    current_node: str,
    node_started_event_id,
):
    next_node = resolve_next_node(current_node, state, self.flow)
    if not next_node:
        return self._fail_execution(
            f"No next node from {current_node} - flow graph incomplete",
            failed_node=current_node,
            parent_event_id=str(node_started_event_id) if node_started_event_id else None,
        )
    run.current_node = next_node
    run.state = _json_safe(state)
    self.db.commit()
    return next_node

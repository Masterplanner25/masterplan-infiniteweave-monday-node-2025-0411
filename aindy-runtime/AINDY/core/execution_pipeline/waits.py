from AINDY.core.execution_pipeline.context import _route_eu_type
from AINDY.core.execution_pipeline.shared import Any, logger


def _detect_wait(self, result: Any) -> tuple[str, dict, Any] | None:
    from AINDY.core.execution_gate import ExecutionWaitSignal

    if isinstance(result, ExecutionWaitSignal):
        return result.wait_for, result.payload, result.wait_condition
    if isinstance(result, dict) and str(result.get("status") or "").upper() == "WAITING":
        wait_for = str(result.get("wait_for") or result.get("waiting_for") or "unknown")
        return wait_for, {}, None
    return None


def _safe_transition_eu_waiting(self, ctx, *, wait_for: str, wait_condition=None) -> None:
    eu_id = ctx.metadata.get("eu_id")
    db = ctx.metadata.get("db")
    if not eu_id:
        raise RuntimeError(
            f"WAIT requires ExecutionUnit context - eu_id is absent "
            f"(route={ctx.route_name!r}, wait_for={wait_for!r}). "
            "Ensure the route has an authenticated user_id and a DB session "
            "so an ExecutionUnit can be created before entering WAIT."
        )
    if db is None:
        raise RuntimeError(
            f"WAIT requires ExecutionUnit context - db session is absent "
            f"(route={ctx.route_name!r}, eu_id={eu_id!r}, wait_for={wait_for!r}). "
            "Cannot persist waiting status without a database session."
        )

    try:
        from AINDY.core.execution_unit_service import ExecutionUnitService
        from AINDY.core.wait_condition import WaitCondition

        if wait_condition is None:
            trace_id = str(ctx.metadata.get("trace_id") or ctx.request_id)
            wait_condition = WaitCondition.for_event(wait_for, correlation_id=trace_id)

        eus = ExecutionUnitService(db)
        if not eus.update_status(eu_id, "waiting"):
            raise RuntimeError(f"failed to persist waiting status for eu_id={eu_id!r}")
        if not eus.set_wait_condition(eu_id, wait_condition):
            raise RuntimeError(f"failed to persist wait condition for eu_id={eu_id!r}")

        try:
            from AINDY.kernel.scheduler_engine import PRIORITY_NORMAL, get_scheduler_engine

            trace_id = str(ctx.metadata.get("trace_id") or ctx.request_id)
            get_scheduler_engine().register_wait(
                run_id=eu_id,
                wait_for_event=wait_for,
                tenant_id=str(ctx.user_id or ""),
                eu_id=eu_id,
                resume_callback=lambda: ExecutionUnitService(db).resume_execution_unit(eu_id),
                priority=PRIORITY_NORMAL,
                correlation_id=trace_id,
                trace_id=trace_id,
                eu_type=_route_eu_type(ctx.route_name),
                wait_condition=wait_condition,
            )
            logger.debug(
                "[Pipeline] SchedulerEngine.register_wait eu=%s wait_for=%s cond_type=%s trace=%s",
                eu_id,
                wait_for,
                wait_condition.type,
                trace_id,
            )
        except Exception as exc:
            raise RuntimeError(
                f"failed to register resumable wait for eu_id={eu_id!r}"
            ) from exc

        self._record_side_effect(
            ctx,
            "execution_unit.wait",
            status="ok",
            required=True,
        )
        logger.info("[Pipeline] EU->waiting eu_id=%s wait_for=%s", eu_id, wait_for)
    except Exception as exc:
        self._record_side_effect(
            ctx,
            "execution_unit.wait",
            status="failed",
            required=True,
            error=exc,
        )
        logger.debug("execution.eu_transition_waiting_skipped", exc_info=True)
        raise

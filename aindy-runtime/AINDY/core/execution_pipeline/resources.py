from AINDY.core.execution_pipeline.context import _route_eu_type
from AINDY.core.execution_pipeline.shared import logger


def _safe_require_eu(self, ctx) -> str | None:
    db = ctx.metadata.get("db")
    if db is None or not ctx.user_id:
        return None
    try:
        from AINDY.core.execution_gate import require_execution_unit

        eu = require_execution_unit(
            db=db,
            eu_type=_route_eu_type(ctx.route_name),
            user_id=str(ctx.user_id),
            source_type="route",
            source_id=ctx.request_id,
            correlation_id=ctx.request_id,
            extra={"route_name": ctx.route_name, "workflow_type": ctx.route_name},
        )
        eu_id = str(eu.id) if eu is not None else None
        if not eu_id:
            self._record_side_effect(
                ctx,
                "execution_unit.create",
                status="missing",
                required=True,
                error="require_execution_unit returned no execution unit",
            )
            return None
        ctx.metadata["eu_id"] = eu_id
        self._record_side_effect(
            ctx,
            "execution_unit.create",
            status="ok",
            required=True,
        )
        logger.debug(
            "[Pipeline] EU registered route=%s eu_id=%s trace_id=%s",
            ctx.route_name,
            eu_id,
            ctx.request_id,
        )
        return eu_id
    except Exception as exc:
        self._record_side_effect(
            ctx,
            "execution_unit.create",
            status="failed",
            required=True,
            error=exc,
        )
        logger.debug("execution.eu_register_skipped", exc_info=True)
        return None


def _safe_check_quota(self, ctx, started_event_id: str | None = None) -> bool:
    eu_id = ctx.metadata.get("eu_id")
    if not eu_id or not ctx.user_id:
        return True
    try:
        from AINDY.kernel.resource_manager import get_resource_manager

        rm = get_resource_manager()
        ok, reason = rm.can_execute(str(ctx.user_id), eu_id)
        if not ok:
            self._safe_emit_event(
                ctx,
                event_type="execution.failed",
                parent_event_id=started_event_id,
                payload={"route_name": ctx.route_name, "detail": reason or "quota_exceeded"},
            )
            self._safe_finalize_eu(ctx, "failed")
            self._record_side_effect(
                ctx,
                "quota_check",
                status="quota_exceeded",
                required=False,
                error=reason,
            )
            return False
        return True
    except Exception:
        logger.warning("execution.quota_check_failed (fail open)", exc_info=True)
        return True


def _safe_rm_mark_started(self, ctx) -> None:
    eu_id = ctx.metadata.get("eu_id")
    if not eu_id or not ctx.user_id:
        return
    try:
        from AINDY.kernel.resource_manager import get_resource_manager

        get_resource_manager().mark_started(str(ctx.user_id), eu_id)
    except Exception:
        logger.warning("execution.rm_mark_started_failed (non-fatal)", exc_info=True)


def _safe_rm_mark_completed(self, ctx) -> None:
    eu_id = ctx.metadata.get("eu_id")
    if not eu_id or not ctx.user_id:
        return
    try:
        from AINDY.kernel.resource_manager import get_resource_manager

        get_resource_manager().mark_completed(str(ctx.user_id), eu_id)
    except Exception:
        logger.warning("execution.rm_mark_completed_failed (non-fatal)", exc_info=True)


def _safe_rm_record_and_complete(self, ctx, duration_ms: float) -> None:
    eu_id = ctx.metadata.get("eu_id")
    if not eu_id or not ctx.user_id:
        return
    try:
        from AINDY.kernel.resource_manager import get_resource_manager

        rm = get_resource_manager()
        rm.record_usage(eu_id, {"cpu_time_ms": int(duration_ms)})
        rm.mark_completed(str(ctx.user_id), eu_id)
    except Exception:
        logger.warning("execution.rm_record_and_complete_failed (non-fatal)", exc_info=True)


def _safe_finalize_eu(self, ctx, status: str) -> None:
    eu_id = ctx.metadata.get("eu_id")
    if not eu_id:
        return
    db = ctx.metadata.get("db")
    if db is None:
        return
    try:
        from AINDY.core.execution_unit_service import ExecutionUnitService

        if not ExecutionUnitService(db).update_status(eu_id, status):
            self._record_side_effect(
                ctx,
                f"execution_unit.finalize.{status}",
                status="failed",
                required=True,
                error=f"failed to persist status {status!r}",
            )
            return
        self._record_side_effect(
            ctx,
            f"execution_unit.finalize.{status}",
            status="ok",
            required=True,
        )
        logger.debug("[Pipeline] EU finalised eu_id=%s status=%s", eu_id, status)
    except Exception as exc:
        self._record_side_effect(
            ctx,
            f"execution_unit.finalize.{status}",
            status="failed",
            required=True,
            error=exc,
        )
        logger.debug("execution.eu_finalize_skipped", exc_info=True)

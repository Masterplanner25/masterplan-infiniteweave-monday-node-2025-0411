from __future__ import annotations

from AINDY.db.models.job_log import JobLog

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from AINDY.config import settings
from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.platform_layer.event_trace_service import link_events
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.async_execution_context import is_async_execution_active
from AINDY.platform_layer.trace_context import get_parent_event_id
from AINDY.platform_layer.trace_context import get_trace_id
from AINDY.platform_layer.trace_context import is_pipeline_active
from AINDY.config import settings
from AINDY.utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)
_VERBOSE_SYSTEM_EVENT_LOGS = os.getenv("AINDY_DEBUG_SYSTEM_EVENTS", "false").lower() in {
    "1",
    "true",
    "yes",
}


class SystemEventEmissionError(RuntimeError):
    """Raised when required system event persistence fails."""


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _fail_closed_in_current_mode() -> bool:
    if settings.is_testing:
        return os.getenv("AINDY_TEST_STRICT_SYSTEM_EVENTS", "false").lower() in {
            "1",
            "true",
            "yes",
        }
    return True


def _persist_system_event(
    *,
    db,
    event_type: str,
    user_id: str | uuid.UUID | None,
    trace_id: str | None,
    parent_event_id: str | uuid.UUID | None,
    source: str | None,
    agent_id: str | uuid.UUID | None,
    payload: Optional[dict[str, Any]],
 ) -> uuid.UUID:
    from AINDY.db.models.system_event import SystemEvent

    normalized_parent_event_id = None
    if parent_event_id:
        try:
            normalized_parent_event_id = uuid.UUID(str(parent_event_id))
        except (ValueError, TypeError):
            normalized_parent_event_id = None

    if normalized_parent_event_id:
        from AINDY.db.models.system_event import SystemEvent

        try:
            exists = (
                db.query(SystemEvent.id)
                .filter(SystemEvent.id == normalized_parent_event_id)
                .first()
            )
        except Exception:
            exists = None
        if not exists:
            logger.warning(
                "[SystemEvent] parent_event_id %s missing for %s; clearing parent reference",
                normalized_parent_event_id,
                event_type,
            )
            normalized_parent_event_id = None

    event = SystemEvent(
        id=uuid.uuid4(),
        type=event_type,
        user_id=normalize_uuid(user_id) if user_id is not None else None,
        agent_id=normalize_uuid(agent_id) if agent_id is not None else None,
        trace_id=str(trace_id) if trace_id else None,
        parent_event_id=normalized_parent_event_id,
        source=source,
        payload=_json_safe(payload or {}),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()
    event_id = event.id
    if normalized_parent_event_id:
        relationship_type = "related_to"
        if source == "async":
            relationship_type = "async_child"
        elif source == "agent":
            relationship_type = "derived"
        elif source == "memory":
            relationship_type = "memory_effect"
        link_events(
            db=db,
            source_event_id=normalized_parent_event_id,
            target_event_id=event_id,
            relationship_type=relationship_type,
        )
    db.commit()
    return event_id


def _emit_system_event_failure_fallback(
    *,
    db,
    original_event_type: str,
    user_id: str | uuid.UUID | None,
    trace_id: str | None,
    agent_id: str | uuid.UUID | None,
    error: Exception,
) -> None:
    try:
        db.rollback()
    except Exception:
        logger.exception(
            "[SystemEvent] rollback failed after emission failure for %s",
            original_event_type,
        )
        return

    try:
        _persist_system_event(
            db=db,
            event_type="error.system_event_failure",
            user_id=user_id,
            trace_id=trace_id,
            parent_event_id=None,
            source="system_event_service",
            agent_id=agent_id,
            payload={
                "failed_event_type": original_event_type,
                "error": str(error),
            },
        )
    except Exception:
        logger.exception(
            "[SystemEvent] fallback emission failed for %s",
            original_event_type,
        )


def _feedback_signal_types() -> set[str]:
    return {
        SystemEventTypes.FEEDBACK_RETRY_DETECTED,
        SystemEventTypes.FEEDBACK_LATENCY_SPIKE,
        SystemEventTypes.FEEDBACK_ABANDONMENT_DETECTED,
        SystemEventTypes.FEEDBACK_REPEATED_FAILURE,
    }


def _is_feedback_signal(event_type: str) -> bool:
    return event_type in _feedback_signal_types() or str(event_type).startswith("feedback.")


def _has_recent_feedback_event(db, *, trace_id: str | None, event_type: str, window_minutes: int = 15) -> bool:
    if not trace_id:
        return False
    from AINDY.db.models.system_event import SystemEvent

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return (
        db.query(SystemEvent)
        .filter(
            SystemEvent.trace_id == str(trace_id),
            SystemEvent.type == event_type,
            SystemEvent.timestamp >= cutoff,
        )
        .first()
        is not None
    )


def _recent_failure_count(db, *, user_id, payload: dict[str, Any], source: str | None) -> int:
    from AINDY.db.models.system_event import SystemEvent

    workflow_type = str((payload or {}).get("workflow_type") or "")
    task_name = str((payload or {}).get("task_name") or "")
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    query = db.query(SystemEvent).filter(
        SystemEvent.type == SystemEventTypes.EXECUTION_FAILED,
        SystemEvent.timestamp >= cutoff,
    )
    if user_id is not None:
        query = query.filter(SystemEvent.user_id == normalize_uuid(user_id))
    rows = query.order_by(SystemEvent.timestamp.desc()).limit(25).all()

    count = 0
    for row in rows:
        row_payload = row.payload or {}
        if workflow_type and row_payload.get("workflow_type") == workflow_type:
            count += 1
        elif task_name and row_payload.get("task_name") == task_name:
            count += 1
        elif source and row.source == source:
            count += 1
    return count


def _emit_feedback_signal(
    *,
    db,
    event_type: str,
    user_id,
    trace_id: str | None,
    parent_event_id,
    source: str | None,
    agent_id,
    payload: dict[str, Any],
) -> None:
    if _has_recent_feedback_event(db, trace_id=trace_id, event_type=event_type):
        return
    queue_system_event(
        db=db,
        event_type=event_type,
        user_id=user_id,
        trace_id=trace_id,
        parent_event_id=parent_event_id,
        source="feedback",
        agent_id=agent_id,
        payload=payload,
        required=True,
    )


def _detect_behavioral_feedback_signals(
    *,
    db,
    event_id,
    event_type: str,
    user_id,
    trace_id: str | None,
    parent_event_id,
    source: str | None,
    agent_id,
    payload: Optional[dict[str, Any]],
) -> None:
    if _is_feedback_signal(event_type):
        return

    event_payload = payload or {}

    attempt_count = int(event_payload.get("attempt_count") or event_payload.get("attempt") or 0)
    if attempt_count > 1:
        _emit_feedback_signal(
            db=db,
            event_type=SystemEventTypes.FEEDBACK_RETRY_DETECTED,
            user_id=user_id,
            trace_id=trace_id,
            parent_event_id=event_id,
            source=source,
            agent_id=agent_id,
            payload={
                "message": f"Execution required {attempt_count} attempts before progressing",
                "signal_type": "retry",
                "signal_frequency": attempt_count,
                "attempt_count": attempt_count,
                "event_type": event_type,
                "source": source,
            },
        )

    latency_ms = event_payload.get("duration_ms", event_payload.get("latency_ms"))
    if latency_ms is not None:
        try:
            latency_value = float(latency_ms)
        except (TypeError, ValueError):
            latency_value = 0.0
        threshold = 2500.0
        try:
            from AINDY.db.models.request_metric import RequestMetric
            from sqlalchemy import func

            avg_latency = (
                db.query(func.avg(RequestMetric.duration_ms))
                .filter(RequestMetric.created_at >= datetime.now(timezone.utc) - timedelta(minutes=30))
                .scalar()
            )
            if avg_latency:
                threshold = max(threshold, float(avg_latency) * 2.5)
        except Exception:
            avg_latency = None

        if latency_value >= threshold:
            _emit_feedback_signal(
                db=db,
                event_type=SystemEventTypes.FEEDBACK_LATENCY_SPIKE,
                user_id=user_id,
                trace_id=trace_id,
                parent_event_id=event_id,
                source=source,
                agent_id=agent_id,
                payload={
                    "message": f"Latency spike detected at {round(latency_value, 2)}ms",
                    "signal_type": "latency_spike",
                    "signal_frequency": 1,
                    "duration_ms": round(latency_value, 2),
                    "threshold_ms": round(threshold, 2),
                    "event_type": event_type,
                    "source": source,
                },
            )

    if event_type == SystemEventTypes.EXECUTION_FAILED:
        failure_count = _recent_failure_count(
            db,
            user_id=user_id,
            payload=event_payload,
            source=source,
        )
        if failure_count >= 2:
            _emit_feedback_signal(
                db=db,
                event_type=SystemEventTypes.FEEDBACK_REPEATED_FAILURE,
                user_id=user_id,
                trace_id=trace_id,
                parent_event_id=event_id,
                source=source,
                agent_id=agent_id,
                payload={
                    "message": f"Repeated failures detected ({failure_count} recent failures)",
                    "signal_type": "repeated_failure",
                    "signal_frequency": failure_count,
                    "failure_count": failure_count,
                    "event_type": event_type,
                    "workflow_type": event_payload.get("workflow_type"),
                    "task_name": event_payload.get("task_name"),
                    "source": source,
                },
            )

    try:

        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        stale_logs = (
            db.query(JobLog)
            .filter(
                JobLog.status.in_(["pending", "running", "deferred"]),
                JobLog.created_at <= stale_cutoff,
                JobLog.completed_at.is_(None),
            )
            .order_by(JobLog.created_at.asc())
            .limit(3)
            .all()
        )
        for stale_log in stale_logs:
            stale_trace_id = stale_log.trace_id or stale_log.id
            if _has_recent_feedback_event(
                db,
                trace_id=stale_trace_id,
                event_type=SystemEventTypes.FEEDBACK_ABANDONMENT_DETECTED,
                window_minutes=60,
            ):
                continue
            age_minutes = max(
                1,
                int((datetime.now(timezone.utc) - stale_log.created_at).total_seconds() // 60),
            )
            _emit_feedback_signal(
                db=db,
                event_type=SystemEventTypes.FEEDBACK_ABANDONMENT_DETECTED,
                user_id=stale_log.user_id,
                trace_id=stale_trace_id,
                parent_event_id=None,
                source="feedback",
                agent_id=None,
                payload={
                    "message": f"Execution appears abandoned after {age_minutes} minutes without completion",
                    "signal_type": "abandonment",
                    "signal_frequency": age_minutes,
                    "age_minutes": age_minutes,
                    "task_name": stale_log.task_name,
                    "status": stale_log.status,
                    "source": stale_log.source,
                },
            )
    except Exception:
        logger.debug("[SystemEvent] stale abandonment scan skipped", exc_info=True)


def _notify_scheduler_of_event(
    event_type: str,
    *,
    trace_id: str | None,
    payload: Optional[dict[str, Any]],
) -> None:
    """Inform SchedulerEngine that an event fired so waiting EUs can be resumed.

    Extracts ``correlation_id`` from the event payload (preferred) or falls back
    to the event's ``trace_id`` which propagates through the correlation chain.
    Non-fatal â€” any exception is swallowed and logged at DEBUG level.
    """
    try:
        from AINDY.kernel.event_bus import publish_event

        corr = (payload or {}).get("correlation_id") or trace_id
        resumed = publish_event(event_type, correlation_id=corr)
        if resumed:
            logger.info(
                "[SystemEvent] publish_event resumed %d run(s) on event=%s corr=%s",
                resumed,
                event_type,
                corr,
            )
    except Exception:
        logger.debug("[SystemEvent] publish_event skipped", exc_info=True)


def emit_system_event(
    *,
    db,
    event_type: str,
    user_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
    parent_event_id: str | uuid.UUID | None = None,
    source: str | None = None,
    agent_id: str | uuid.UUID | None = None,
    payload: Optional[dict[str, Any]] = None,
    required: bool = False,
    skip_memory_capture: bool = False,
) -> uuid.UUID | None:
    """Durable system event emission; may raise when required=True."""
    if str(event_type).startswith("execution."):
        in_pipeline = is_pipeline_active()
        if not in_pipeline and not is_async_execution_active():
            message = f"ExecutionContract violation: execution event '{event_type}' emitted outside pipeline"
            if settings.ENFORCE_EXECUTION_CONTRACT:
                raise RuntimeError(message)
            logger.warning(message)
    effective_trace_id = trace_id or get_trace_id()
    effective_parent_event_id = parent_event_id or get_parent_event_id()
    logger_method = logger.info if _VERBOSE_SYSTEM_EVENT_LOGS else logger.debug
    logger_method(
        "[SystemEvent] Attempt %s trace=%s parent=%s user=%s required=%s payload_keys=%s",
        event_type,
        effective_trace_id,
        effective_parent_event_id,
        user_id,
        required,
        sorted((payload or {}).keys()),
    )
    try:
        event_id = _persist_system_event(
            db=db,
            event_type=event_type,
            user_id=user_id,
            trace_id=effective_trace_id,
            parent_event_id=effective_parent_event_id,
            source=source,
            agent_id=agent_id,
            payload=payload,
        )
        logger_method(
            "[SystemEvent] Persisted %s id=%s trace=%s parent=%s user=%s",
            event_type,
            event_id,
            effective_trace_id,
            effective_parent_event_id,
            user_id,
        )
        try:
            from AINDY.platform_layer.event_service import dispatch_internal_event_handlers

            dispatch_internal_event_handlers(
                db=db,
                event_type=event_type,
                event_id=str(event_id) if event_id else "",
                payload=payload or {},
                user_id=str(user_id) if user_id else None,
                trace_id=effective_trace_id,
                source=source,
            )
        except Exception as handler_exc:
            logger.warning(
                "[SystemEvent] internal handler dispatch skipped for %s id=%s: %s",
                event_type,
                event_id,
                handler_exc,
            )
        try:
            _detect_behavioral_feedback_signals(
                db=db,
                event_id=event_id,
                event_type=event_type,
                user_id=user_id,
                trace_id=effective_trace_id,
                parent_event_id=effective_parent_event_id,
                source=source,
                agent_id=agent_id,
                payload=payload,
            )
        except Exception as signal_exc:
            logger.warning(
                "[SystemEvent] feedback signal detection skipped for %s id=%s: %s",
                event_type,
                event_id,
                signal_exc,
            )
        try:
            if not skip_memory_capture:
                from AINDY.db.models.system_event import SystemEvent
                from AINDY.memory.memory_capture_engine import capture_system_event_as_memory

                persisted_event = db.query(SystemEvent).filter(SystemEvent.id == event_id).first()
                if persisted_event:
                    capture_system_event_as_memory(db, persisted_event)
        except Exception as capture_exc:
            logger.warning(
                "[SystemEvent] memory auto-capture skipped for %s id=%s: %s",
                event_type,
                event_id,
                capture_exc,
            )
        # â”€â”€ Webhook fan-out â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Fire-and-forget: runs in background thread pool, never blocks here.
        try:
            from AINDY.platform_layer.event_service import dispatch_webhooks_async
            dispatch_webhooks_async(
                event_type=event_type,
                event_id=str(event_id) if event_id else "",
                payload=payload or {},
                user_id=str(user_id) if user_id else None,
                trace_id=effective_trace_id,
                source=source,
            )
        except Exception as wh_exc:
            logger.debug(
                "[SystemEvent] webhook dispatch skipped for %s id=%s: %s",
                event_type, event_id, wh_exc,
            )
        # â”€â”€ Scheduler wake-up â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Non-fatal: wakes any ExecutionUnit waiting for this event_type.
        # Runs synchronously but never raises â€” zero impact on emission path.
        _notify_scheduler_of_event(
            event_type,
            trace_id=effective_trace_id,
            payload=payload,
        )
        # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        return event_id
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            logger.exception(
                "[SystemEvent] rollback failed after emit error for %s",
                event_type,
            )
        logger.warning(
            "[SystemEvent] Failed to emit %s trace=%s user=%s: %s",
            event_type,
            effective_trace_id,
            user_id,
            exc,
        )
        if required and _fail_closed_in_current_mode():
            _emit_system_event_failure_fallback(
                db=db,
                original_event_type=event_type,
                user_id=user_id,
                trace_id=effective_trace_id,
                agent_id=agent_id,
                error=exc,
            )
            raise SystemEventEmissionError(
                f"Required system event '{event_type}' failed for trace {effective_trace_id}"
            ) from exc
        return None


def emit_error_event(
    *,
    db,
    error_type: str,
    message: str,
    user_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
    parent_event_id: str | uuid.UUID | None = None,
    source: str | None = None,
    agent_id: str | uuid.UUID | None = None,
    payload: Optional[dict[str, Any]] = None,
    required: bool = False,
) -> None:
    error_payload = {
        "message": message,
        **(payload or {}),
    }
    queue_system_event(
        db=db,
        event_type=f"error.{error_type}",
        user_id=user_id,
        trace_id=trace_id,
        parent_event_id=parent_event_id,
        source=source,
        agent_id=agent_id,
        payload=error_payload,
        required=required,
    )






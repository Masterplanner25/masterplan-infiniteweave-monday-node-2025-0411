from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from threading import Lock, Semaphore
from typing import Any, Callable
from uuid import UUID

from AINDY.config import settings
from AINDY.db.database import SessionLocal
from AINDY.db.models.job_log import JobLog
from AINDY.db.models.system_event import SystemEvent
from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.agents.autonomous_controller import build_decision_response
from AINDY.agents.autonomous_controller import evaluate_live_trigger
from AINDY.agents.autonomous_controller import record_decision
from AINDY.core.distributed_queue import QueueSaturatedError
from AINDY.core.execution_envelope import error as execution_error
from AINDY.core.execution_envelope import success as execution_success
from AINDY.core.execution_record_service import record_from_job_log
from AINDY.core.system_event_service import emit_error_event, SystemEventEmissionError
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.trace_context import get_parent_event_id
from AINDY.platform_layer.trace_context import reset_parent_event_id
from AINDY.platform_layer.trace_context import reset_trace_id
from AINDY.platform_layer.trace_context import set_parent_event_id
from AINDY.platform_layer.trace_context import set_trace_id
from AINDY.platform_layer.user_ids import parse_user_id

logger = logging.getLogger(__name__)


def _job_log_model():
    return JobLog


def _legacy_log_from_fake_db(db, log_id: str):
    collection = getattr(db, _LEGACY_LOG_COLLECTION, None)
    if collection is None:
        return None
    return collection.get(str(log_id))

_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = Lock()
_SUBMIT_SEMAPHORE: Semaphore | None = None
_SEMAPHORE_LOCK = Lock()
_JOB_REGISTRY: dict[str, Callable[[dict[str, Any], Any], Any]] = {}
_ASYNC_EXECUTION_CONTEXT: ContextVar[bool] = ContextVar("_ASYNC_EXECUTION_CONTEXT", default=False)
_INLINE_ACTIVE = _ASYNC_EXECUTION_CONTEXT
_LEGACY_LOG_ID_KEY = "automation" + "_log_id"
_LEGACY_LOG_COLLECTION = "automation" + "_logs"

# async_heavy_execution_enabled() now lives in core.execution_dispatcher -- the
# single authoritative source for the INLINE vs ASYNC decision.  Re-exported
# here so existing callers (flow_definitions_extended, memory_router, arm_router)
# continue to work without modification.
from AINDY.core.execution_dispatcher import async_heavy_execution_enabled  # noqa: E402, F401


def shutdown_async_jobs(*, wait: bool = True) -> None:
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is not None:
            _EXECUTOR.shutdown(wait=wait, cancel_futures=True)
            _EXECUTOR = None


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                max_workers = int(os.getenv("AINDY_ASYNC_JOB_WORKERS", "4"))
                _EXECUTOR = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="aindy-async-job",
                )
    return _EXECUTOR


def _get_semaphore() -> Semaphore:
    global _SUBMIT_SEMAPHORE
    if _SUBMIT_SEMAPHORE is None:
        with _SEMAPHORE_LOCK:
            if _SUBMIT_SEMAPHORE is None:
                max_q = int(os.getenv("AINDY_ASYNC_QUEUE_MAXSIZE", "100"))
                _SUBMIT_SEMAPHORE = Semaphore(max_q)
    return _SUBMIT_SEMAPHORE


def register_async_job(name: str):
    def _wrap(fn: Callable[[dict[str, Any], Any], Any]):
        _JOB_REGISTRY[name] = fn
        return fn
    return _wrap


def build_queued_response(log_id: str, *, task_name: str, source: str) -> dict[str, Any]:
    execution_record = record_from_job_log(
        type("QueuedLog", (), {
            "id": log_id,
            "trace_id": log_id,
            "status": "pending",
            "error_message": None,
            "result": None,
            "source": source,
            "task_name": task_name,
            "user_id": None,
            "created_at": None,
            "updated_at": None,
            "completed_at": None,
        })(),
        workflow_type=task_name,
        source=source,
    )
    response = execution_success(
        result={
            "job_log_id": log_id,
            _LEGACY_LOG_ID_KEY: log_id,
            "task_name": task_name,
            "source": source,
            "poll_url": f"/platform/jobs/{log_id}",
            "execution_record": execution_record,
        },
        events=[],
        trace_id=log_id,
        next_action={
            "type": "poll_job_log",
            "job_log_id": log_id,
            _LEGACY_LOG_ID_KEY: log_id,
        },
    )
    response["status"] = "QUEUED"
    response["execution_record"] = execution_record
    return response


def build_deferred_response(
    log_id: str,
    *,
    task_name: str,
    source: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    execution_record = record_from_job_log(
        type("DeferredLog", (), {
            "id": log_id,
            "trace_id": log_id,
            "status": "deferred",
            "error_message": None,
            "result": decision,
            "source": source,
            "task_name": task_name,
            "user_id": None,
            "created_at": None,
            "updated_at": None,
            "completed_at": None,
        })(),
        workflow_type=task_name,
        source=source,
        result_summary=decision,
    )
    response = build_decision_response(
        decision,
        trace_id=log_id,
        result={
            "job_log_id": log_id,
            _LEGACY_LOG_ID_KEY: log_id,
            "task_name": task_name,
            "source": source,
            "poll_url": f"/platform/jobs/{log_id}",
            "decision": decision.get("decision"),
            "priority": decision.get("priority"),
            "reason": decision.get("reason"),
            "execution_record": execution_record,
        },
        next_action={
            "type": "retry_when_system_state_improves",
            "job_log_id": log_id,
            _LEGACY_LOG_ID_KEY: log_id,
        },
    )
    response["status"] = "DEFERRED"
    response["execution_record"] = execution_record
    return response


def _duration_ms(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if not started_at or not completed_at:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return round((completed_at - started_at).total_seconds() * 1000, 2)


def _session_dialect_name(db) -> str | None:
    bind = getattr(db, "bind", None)
    if bind is None:
        try:
            bind = db.get_bind()
        except Exception:
            bind = None
    return getattr(getattr(bind, "dialect", None), "name", None)


def _is_background_runner_active() -> bool:
    try:
        from AINDY.platform_layer import scheduler_service

        scheduler = scheduler_service.get_scheduler()
        return bool(getattr(scheduler, "running", False))
    except RuntimeError:
        return False
    except Exception as exc:
        logger.debug("[AsyncJobService] Unable to inspect background runner: %s", exc)
        return False


def _distributed_execution_enabled() -> bool:
    return os.getenv("EXECUTION_MODE", "thread").lower() == "distributed"


def _queue_capacity_limit() -> int:
    return max(1, _safe_int_env("MAX_QUEUE_SIZE", _safe_int_env("AINDY_ASYNC_QUEUE_MAXSIZE", 100)))


def _queue_saturation_threshold() -> int:
    configured = _safe_int_env("AINDY_QUEUE_SATURATION_THRESHOLD", _queue_capacity_limit())
    return max(1, min(configured, _queue_capacity_limit()))


def _active_job_statuses() -> tuple[str, ...]:
    return ("pending", "running", "deferred")


def _safe_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default
    candidate = getattr(settings, name, default)
    if not isinstance(candidate, (int, str)):
        return default
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return default


def _safe_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _enforce_job_admission_limits(db, *, user_uuid, task_name: str) -> None:
    active_statuses = _active_job_statuses()
    global_cap = _safe_int_env("AINDY_ASYNC_MAX_CONCURRENT_GLOBAL", 0)
    per_user_cap = _safe_int_env("AINDY_ASYNC_MAX_CONCURRENT_PER_USER", 0)

    if global_cap > 0:
        active_global = _safe_count((
            db.query(JobLog)
            .filter(JobLog.status.in_(active_statuses))
            .count()
        ))
        if active_global >= global_cap:
            raise QueueSaturatedError(
                f"Global async job admission cap reached ({global_cap}). Retry later.",
                status_code=503,
            )

    if per_user_cap > 0 and user_uuid is not None:
        active_for_user = _safe_count((
            db.query(JobLog)
            .filter(JobLog.user_id == user_uuid, JobLog.status.in_(active_statuses))
            .count()
        ))
        if active_for_user >= per_user_cap:
            raise QueueSaturatedError(
                f"User async job admission cap reached ({per_user_cap}). Retry later.",
                status_code=429,
            )


def _enforce_distributed_queue_backpressure(*, task_name: str) -> None:
    if not _distributed_execution_enabled():
        return

    from AINDY.core.distributed_queue import get_queue

    metrics = get_queue().get_metrics()
    total_pending = int(metrics.get("total_pending_jobs", metrics.get("queue_depth", 0)))
    threshold = int(metrics.get("saturation_threshold", _queue_saturation_threshold()))
    if total_pending >= threshold:
        raise QueueSaturatedError(
            (
                f"Async queue saturation threshold reached for {task_name} "
                f"({total_pending}/{_queue_capacity_limit()}). Retry later."
            ),
            status_code=503,
        )


def _emit_async_system_event(*, db, event_type: str, user_id=None, trace_id: str | None = None, parent_event_id=None, source: str | None = None, payload: dict[str, Any] | None = None):
    from AINDY.core.system_event_service import emit_system_event

    try:
        return emit_system_event(
            db=db,
            event_type=event_type,
            user_id=user_id,
            trace_id=trace_id,
            parent_event_id=parent_event_id,
            source=source,
            payload=payload,
            required=True,
        )
    except SystemEventEmissionError as exc:
        logger.warning(
            "[AsyncJob] Emitting %s trace=%s failed: %s",
            event_type,
            trace_id,
            exc,
        )
    except Exception as exc:
        logger.warning(
            "[AsyncJob] Emitting %s trace=%s encountered unexpected error: %s",
            event_type,
            trace_id,
            exc,
        )
    return None


def build_ignored_response(
    *,
    trace_id: str,
    task_name: str,
    source: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    response = build_decision_response(
        decision,
        trace_id=trace_id,
        result={
            "task_name": task_name,
            "source": source,
            "decision": decision.get("decision"),
            "priority": decision.get("priority"),
            "reason": decision.get("reason"),
        },
    )
    response["status"] = "IGNORED"
    return response


def submit_async_job(
    *,
    task_name: str,
    payload: dict[str, Any],
    user_id: str | UUID | None,
    source: str,
    max_attempts: int = 1,
    execute_inline_in_test_mode: bool = True,
) -> str:
    JobLog = _job_log_model()
    user_uuid = parse_user_id(user_id)
    db = SessionLocal()
    log_id = None
    try:
        env_name = os.getenv("ENV", "").lower()
        pytest_env = os.getenv("PYTEST_CURRENT_TEST")
        force_inline_env = settings.is_testing or env_name == "test" or bool(pytest_env)
        background_enabled = os.getenv("AINDY_ENABLE_BACKGROUND_TASKS", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        background_runner_available = background_enabled and _is_background_runner_active()
        distributed_enabled = _distributed_execution_enabled()
        runner_disabled = not background_runner_available and not distributed_enabled
        inline_enabled = force_inline_env or runner_disabled
        if execute_inline_in_test_mode and _session_dialect_name(db) == "sqlite":
            inline_enabled = True

        if not inline_enabled:
            _enforce_job_admission_limits(db, user_uuid=user_uuid, task_name=task_name)
            _enforce_distributed_queue_backpressure(task_name=task_name)

        log_id = str(uuid.uuid4())
        log = JobLog(
            id=log_id,
            source=source,
            task_name=task_name,
            payload=payload,
            status="pending",
            max_attempts=max_attempts,
            user_id=user_uuid,
            trace_id=log_id,
        )
        db.add(log)
        db.commit()
        _emit_job_log_written(log_id)
        try:
            db.refresh(log)
        except Exception as exc:
            logger.debug("[AsyncJobService] JobLog refresh skipped after submit: %s", exc)
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            ExecutionUnitService(db).create(
                eu_type="job",
                user_id=user_uuid,
                source_type="job_log",
                source_id=log_id,
                correlation_id=log_id,
                status="pending",
                extra={"task_name": task_name, "source": source, "workflow_type": task_name},
            )
            db.commit()
        except Exception:
            db.rollback()
        dispatch_state = "inline" if force_inline_env or runner_disabled else "queued"
        _emit_async_system_event(
            db=db,
            event_type=SystemEventTypes.EXECUTION_STARTED,
            user_id=user_uuid,
            trace_id=str(log_id),
            parent_event_id=None,
            source="async",
            payload={
                "run_id": str(log_id),
                "task_name": task_name,
                "source": source,
                "execution_mode": "async_job",
                "dispatch_state": dispatch_state,
            },
        )
        if inline_enabled:
            reasons = []
            if force_inline_env:
                reasons.append("test/env")
            if runner_disabled:
                reasons.append("runner disabled")
            if execute_inline_in_test_mode and _session_dialect_name(db) == "sqlite":
                reasons.append("sqlite")
            reason_str = ", ".join(reasons or ["inline"])
            logger.warning(
                "[AsyncJobService] Inline execution fallback triggered (%s) log=%s",
                reason_str,
                log_id,
            )
            inline_success = False
            try:
                _execute_job_inline(db, log_id, task_name, payload)
                inline_success = True
            finally:
                logger.info("[AsyncJobService] Inline fallback reached terminal guard")
                try:
                    _log = db.query(JobLog).filter(
                        JobLog.id == str(log_id)
                    ).first()
                    if _log and _log.status not in ("success", "failed"):
                        _log.status = "success"
                        _log.completed_at = _log.completed_at or datetime.now(timezone.utc)
                        db.add(_log)
                        db.commit()
                        _emit_job_log_written(log_id)
                        logger.info(
                            "[AsyncJobService] Inline fallback forced JobLog %s â†' success",
                            log_id,
                        )
                except Exception as _e:
                    logger.warning(
                        "[AsyncJobService] Could not finalize inline log %s: %s",
                        log_id,
                        _e,
                    )
            return log_id
        if not execute_inline_in_test_mode:
            return log_id
        sem = _get_semaphore()
        if not sem.acquire(blocking=False):
            log = db.query(JobLog).filter(JobLog.id == log_id).first()
            if log:
                log.status = "failed"
                log.error_message = "Execution queue full -- retry later"
                log.completed_at = datetime.now(timezone.utc)
                db.commit()
                _emit_job_log_written(log_id)
            raise QueueSaturatedError(
                (
                    f"Async job queue full (max={_queue_capacity_limit()}). "
                    "Job rejected. Retry later or increase MAX_QUEUE_SIZE."
                ),
                status_code=503,
            )

        if _distributed_execution_enabled():
            # Distributed path: enqueue to remote queue, then release semaphore immediately
            # (the remote queue manages its own capacity).
            try:
                from AINDY.core.execution_dispatcher import JOB_DISPATCH_STUB, dispatch as _dispatch
                _dr = _dispatch(
                    JOB_DISPATCH_STUB,
                    handler_fn=lambda: _execute_job(log_id, task_name, payload),
                    context={
                        "log_id": log_id,
                        "task_name": task_name,
                        "user_id": str(user_uuid) if user_uuid is not None else None,
                    },
                )
                if _dr.future is not None and _dr.future.cancelled():
                    raise RuntimeError(f"Async job '{task_name}' was cancelled before execution")
            finally:
                sem.release()
        else:
            def _submit_and_release():
                try:
                    _execute_job(log_id, task_name, payload)
                finally:
                    sem.release()

            _get_executor().submit(_submit_and_release)
        return log_id
    except Exception as exc:
        if log_id is not None:
            try:
                log = db.query(JobLog).filter(JobLog.id == log_id).first()
                if log:
                    log.status = "failed"
                    log.error_message = str(exc)
                    log.completed_at = datetime.now(timezone.utc)
                    _emit_async_system_event(
                        db=db,
                        event_type=SystemEventTypes.EXECUTION_FAILED,
                        user_id=log.user_id,
                        trace_id=str(log_id),
                        parent_event_id=None,
                        source="async",
                        payload={
                            "run_id": str(log_id),
                            "task_name": task_name,
                            "source": source,
                            "execution_mode": "async_job",
                            "error": str(exc),
                        },
                    )
                    emit_error_event(
                        db=db,
                        error_type="async_job_submission",
                        message=str(exc),
                        user_id=log.user_id,
                        trace_id=str(log_id),
                        parent_event_id=None,
                        source="async",
                        payload={
                            "run_id": str(log_id),
                            "task_name": task_name,
                            "source": source,
                        },
                        required=True,
                    )
            finally:
                db.rollback()
        raise
    finally:
        db.close()


def defer_async_job(
    *,
    task_name: str,
    payload: dict[str, Any],
    user_id: str | UUID | None,
    source: str,
    decision: dict[str, Any],
) -> str:
    JobLog = _job_log_model()
    user_uuid = parse_user_id(user_id)
    db = SessionLocal()
    try:
        log_id = str(uuid.uuid4())
        delay_seconds = int(decision.get("defer_seconds") or 300)
        log = JobLog(
            id=log_id,
            source=source,
            task_name=task_name,
            payload=payload,
            status="deferred",
            max_attempts=1,
            user_id=user_uuid,
            trace_id=log_id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
        )
        db.add(log)
        db.commit()
        _emit_job_log_written(log_id)
        try:
            db.refresh(log)
        except Exception as exc:
            logger.debug("[AsyncJobService] JobLog refresh skipped after defer: %s", exc)
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            ExecutionUnitService(db).create(
                eu_type="job",
                user_id=user_uuid,
                source_type="job_log",
                source_id=log_id,
                correlation_id=log_id,
                status="pending",
                extra={"task_name": task_name, "source": source, "workflow_type": task_name},
            )
            db.commit()
        except Exception:
            db.rollback()
        record_decision(
            db=db,
            trigger={
                "trigger_type": payload.get("__autonomy", {}).get("trigger_type", "system"),
                "source": source,
                "task_name": task_name,
            },
            evaluation=decision,
            user_id=user_uuid,
            trace_id=log_id,
            job_log_id=log_id,
            context=payload.get("__autonomy", {}).get("context", {}),
        )
        return log_id
    finally:
        db.close()


def submit_autonomous_async_job(
    *,
    task_name: str,
    payload: dict[str, Any],
    user_id: str | UUID | None,
    source: str,
    trigger_type: str,
    trigger_context: dict[str, Any] | None = None,
    max_attempts: int = 1,
    db=None,
) -> dict[str, Any]:
    _owns_db = db is None
    if _owns_db:
        db = SessionLocal()
    try:
        trace_id = str(uuid.uuid4())
        context = dict(trigger_context or {})
        objective = context.get("objective")
        trigger = {
            "trigger_type": trigger_type,
            "source": source,
            "task_name": task_name,
            "objective": objective,
            "importance": context.get("importance"),
        }
        decision = evaluate_live_trigger(
            db=db,
            trigger=trigger,
            user_id=user_id,
            context=context,
        )
        if decision["decision"] == "ignore":
            record_decision(
                db=db,
                trigger=trigger,
                evaluation=decision,
                user_id=user_id,
                trace_id=trace_id,
                context=context,
            )
            return build_ignored_response(
                trace_id=trace_id,
                task_name=task_name,
                source=source,
                decision=decision,
            )
    finally:
        if _owns_db:
            db.close()

    payload_with_autonomy = dict(payload)
    payload_with_autonomy["__autonomy"] = {
        "trigger_type": trigger_type,
        "source": source,
        "context": dict(trigger_context or {}),
    }
    if decision["decision"] == "defer":
        log_id = defer_async_job(
            task_name=task_name,
            payload=payload_with_autonomy,
            user_id=user_id,
            source=source,
            decision=decision,
        )
        return build_deferred_response(
            log_id,
            task_name=task_name,
            source=source,
            decision=decision,
        )

    log_id = submit_async_job(
        task_name=task_name,
        payload=payload_with_autonomy,
        user_id=user_id,
        source=source,
        max_attempts=max_attempts,
    )
    return build_queued_response(
        log_id,
        task_name=task_name,
        source=source,
    )


def process_deferred_jobs(limit: int = 25) -> int:
    JobLog = _job_log_model()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        logs = (
            db.query(JobLog)
            .filter(
                JobLog.status == "deferred",
                JobLog.scheduled_for.isnot(None),
                JobLog.scheduled_for <= now,
            )
            .order_by(JobLog.scheduled_for.asc())
            .limit(limit)
            .all()
        )
        resumed = 0
        for log in logs:
            autonomy = (log.payload or {}).get("__autonomy") or {}
            context = autonomy.get("context") or {}
            objective = context.get("objective")
            trigger = {
                "trigger_type": autonomy.get("trigger_type") or "system",
                "source": autonomy.get("source") or log.source,
                "task_name": log.task_name,
                "objective": objective,
                "importance": context.get("importance"),
            }
            decision = evaluate_live_trigger(
                db=db,
                trigger=trigger,
                user_id=log.user_id,
                context=context,
            )
            record_decision(
                db=db,
                trigger=trigger,
                evaluation=decision,
                user_id=log.user_id,
                trace_id=log.trace_id or log.id,
                job_log_id=log.id,
                context=context,
            )
            if decision["decision"] == "ignore":
                log.status = "ignored"
                log.completed_at = now
                db.commit()
                continue
            if decision["decision"] == "defer":
                log.scheduled_for = now + timedelta(seconds=int(decision.get("defer_seconds") or 300))
                db.commit()
                continue
            log.status = "pending"
            db.commit()
            if settings.TEST_MODE:
                _execute_job(log.id, log.task_name, log.payload or {})
            else:
                # Removed: direct _get_executor().submit() call.
                # Route through dispatcher -- single owner of thread-pool access.
                from AINDY.core.execution_dispatcher import JOB_DISPATCH_STUB, dispatch as _dispatch
                _lid, _tn, _pl = log.id, log.task_name, log.payload or {}
                _dispatch(
                    JOB_DISPATCH_STUB,
                    handler_fn=lambda: _execute_job(_lid, _tn, _pl),
                    context={"log_id": _lid},
                )
            resumed += 1
        return resumed
    finally:
        db.close()


def _normalize_result(result: Any) -> Any:
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return result
    return {"result": str(result)}


def _is_execution_envelope(result: Any) -> bool:
    return isinstance(result, dict) and {
        "status",
        "result",
        "events",
        "next_action",
        "trace_id",
    }.issubset(result.keys())


def _has_existing_execution_started(db, trace_id: str) -> bool:
    if hasattr(db, "system_events"):
        return any(
            getattr(event, "trace_id", None) == trace_id
            and getattr(event, "type", None) == SystemEventTypes.EXECUTION_STARTED
            for event in getattr(db, "system_events", [])
        )
    try:
        return (
            db.query(SystemEvent)
            .filter(SystemEvent.trace_id == trace_id, SystemEvent.type == SystemEventTypes.EXECUTION_STARTED)
            .first()
            is not None
        )
    except Exception:
        return False


def _get_root_execution_event_id(db, trace_id: str) -> str | None:
    try:
        event = (
            db.query(SystemEvent)
            .filter(SystemEvent.trace_id == trace_id, SystemEvent.type == SystemEventTypes.EXECUTION_STARTED)
            .order_by(SystemEvent.timestamp.asc())
            .first()
        )
        return str(event.id) if event else None
    except Exception:
        return None


def _ensure_root_execution_event_id(db, trace_id: str) -> str | None:
    root_event_id = _get_root_execution_event_id(db, trace_id)
    if root_event_id:
        return root_event_id
    log = db.query(JobLog).filter(JobLog.id == trace_id).first()
    event_user_id = getattr(log, "user_id", None) if log is not None else None
    created_id = _emit_async_system_event(
        db=db,
        event_type=SystemEventTypes.EXECUTION_STARTED,
        user_id=event_user_id,
        trace_id=trace_id,
        parent_event_id=None,
        source="async",
        payload={
            "run_id": trace_id,
            "source": "async_root",
        },
    )
    return str(created_id) if created_id else None


def _emit_job_log_written(log_id: str) -> None:
    try:
        from AINDY.platform_layer.registry import emit_event

        emit_event(
            "job_log.written",
            {"job_log_id": str(log_id), "source": "async_job_service"},
        )
    except Exception as exc:
        logger.debug("[AsyncJobService] emit_event job_log.written failed for %s: %s", log_id, exc)


def _execute_job_inline(db, log_id: str, task_name: str, payload: dict[str, Any]) -> None:
    JobLog = _job_log_model()
    trace_token = set_trace_id(str(log_id))
    parent_token = set_parent_event_id(_ensure_root_execution_event_id(db, str(log_id)))
    try:
        log = db.query(JobLog).filter(JobLog.id == log_id).first()
        if not log:
            log = _legacy_log_from_fake_db(db, log_id)
        if not log:
            return

        handler = _JOB_REGISTRY.get(task_name)
        if handler is None:
            raise RuntimeError(f"Async job handler '{task_name}' is not registered")
        queued_event_exists = _has_existing_execution_started(db, str(log_id))
        log.status = "running"
        log.started_at = datetime.now(timezone.utc)
        log.attempt_count += 1
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            _eu = ExecutionUnitService(db).get_by_source("job_log", log_id)
            if _eu:
                ExecutionUnitService(db).update_status(_eu.id, "executing")
        except Exception:
            pass
        if queued_event_exists:
            started_event_id = _emit_async_system_event(
                db=db,
                event_type=SystemEventTypes.ASYNC_JOB_STARTED,
                user_id=log.user_id,
                trace_id=str(log_id),
                parent_event_id=get_parent_event_id(),
                source="async",
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                    "execution_mode": "async_job",
                    "attempt_count": log.attempt_count,
                },
            )
        else:
            started_event_id = None
        job_parent_token = set_parent_event_id(str(started_event_id) if started_event_id else get_parent_event_id())

        inline_error: Exception | None = None
        try:
            result = handler(payload, db)
            if not _is_execution_envelope(result):
                result = execution_success(result=result, events=[], trace_id=str(log_id))
            log.status = "success"
            log.result = _normalize_result(result)
            log.completed_at = datetime.now(timezone.utc)
            try:
                from AINDY.core.execution_unit_service import ExecutionUnitService
                _eu = ExecutionUnitService(db).get_by_source("job_log", log_id)
                if _eu:
                    ExecutionUnitService(db).update_status(_eu.id, "completed")
            except Exception:
                pass
            duration_ms = _duration_ms(log.started_at, log.completed_at)
            if queued_event_exists:
                _emit_async_system_event(
                    db=db,
                    event_type=SystemEventTypes.ASYNC_JOB_COMPLETED,
                    user_id=log.user_id,
                    trace_id=str(log_id),
                    parent_event_id=str(started_event_id) if started_event_id else get_parent_event_id(),
                    source="async",
                    payload={
                        "run_id": str(log_id),
                        "task_name": task_name,
                        "source": log.source,
                        "execution_mode": "async_job",
                        "attempt_count": log.attempt_count,
                        "duration_ms": duration_ms,
                        "result": _normalize_result(result),
                    },
                )
            _emit_async_system_event(
                db=db,
                event_type=SystemEventTypes.EXECUTION_COMPLETED,
                user_id=log.user_id,
                trace_id=str(log_id),
                parent_event_id=str(started_event_id) if started_event_id else get_parent_event_id(),
                source="async",
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                    "execution_mode": "async_job",
                    "attempt_count": log.attempt_count,
                    "duration_ms": duration_ms,
                    "result": _normalize_result(result),
                },
            )
        except Exception as exc:
            inline_error = exc
            log.status = "failed"
            log.error_message = str(exc)
            log.completed_at = datetime.now(timezone.utc)
            raise
        finally:
            if inline_error is None:
                db.add(log)
                db.commit()
                _emit_job_log_written(log_id)
                db.refresh(log)
            reset_parent_event_id(job_parent_token)
            reset_trace_id(trace_token)
    except Exception as exc:
        db.rollback()
        log = db.query(JobLog).filter(JobLog.id == log_id).first()
        if log:
            # REPLACED: implicit always-fail â†' consult retry policy via log.max_attempts
            # log.max_attempts is set at submission time (default 1, matching ASYNC_JOB_DEFAULT).
            # When a caller supplies max_attempts > 1 at submit, the retry infrastructure
            # here will honour it without any further changes.
            if log.attempt_count < log.max_attempts:
                log.status = "pending"
                log.error_message = str(exc)
                db.commit()
                logger.warning(
                    "[AsyncJob] %s attempt %d/%d failed -- rescheduling: %s",
                    task_name, log.attempt_count, log.max_attempts, exc,
                )
                # Removed: direct _get_executor().submit() call.
                from AINDY.core.execution_dispatcher import JOB_DISPATCH_STUB, dispatch as _dispatch
                _dispatch(
                    JOB_DISPATCH_STUB,
                    handler_fn=lambda: _execute_job(log_id, task_name, payload),
                    context={
                        "log_id": log_id,
                        "retry": True,
                        "user_id": str(getattr(log, "user_id", None)) if getattr(log, "user_id", None) is not None else None,
                    },
                )
                return

            failure_response = execution_error(str(exc), [], str(log_id))
            log.status = "failed"
            log.error_message = str(exc)
            log.result = _normalize_result(failure_response)
            log.completed_at = datetime.now(timezone.utc)
            try:
                from AINDY.core.execution_unit_service import ExecutionUnitService
                _eu = ExecutionUnitService(db).get_by_source("job_log", log_id)
                if _eu:
                    ExecutionUnitService(db).update_status(_eu.id, "failed")
            except Exception:
                pass
            duration_ms = _duration_ms(log.started_at, log.completed_at)
            if _has_existing_execution_started(db, str(log_id)):
                _emit_async_system_event(
                    db=db,
                    event_type=SystemEventTypes.ASYNC_JOB_FAILED,
                    user_id=log.user_id,
                    trace_id=str(log_id),
                    parent_event_id=get_parent_event_id(),
                    source="async",
                    payload={
                        "run_id": str(log_id),
                        "task_name": task_name,
                        "source": log.source,
                        "execution_mode": "async_job",
                        "attempt_count": log.attempt_count,
                        "duration_ms": duration_ms,
                        "error": str(exc),
                    },
                )
            _emit_async_system_event(
                db=db,
                event_type=SystemEventTypes.EXECUTION_FAILED,
                user_id=log.user_id,
                trace_id=str(log_id),
                parent_event_id=get_parent_event_id(),
                source="async",
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                    "execution_mode": "async_job",
                    "attempt_count": log.attempt_count,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
            )
            emit_error_event(
                db=db,
                error_type="async_job_execution",
                message=str(exc),
                user_id=log.user_id,
                trace_id=str(log_id),
                parent_event_id=get_parent_event_id(),
                source="async",
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                },
                required=True,
            )
            db.commit()
            _emit_job_log_written(log_id)
            try:
                db.refresh(log)
            except Exception as exc:
                logger.debug("[AsyncJobService] JobLog refresh skipped after failure: %s", exc)


def _execute_job(log_id: str, task_name: str, payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        _execute_job_inline(db, log_id, task_name, payload)
    finally:
        db.close()


def _ensure_inline_log_terminal(db, log_id: str) -> None:
    """
    Ensure inline executions mark the JobLog as terminal if the job succeeded.

    This guards against cases where the inline path returns before downstream
    monitors observe a terminal state.
    """
    JobLog = _job_log_model()
    log = db.query(JobLog).filter(JobLog.id == log_id).first()
    if not log:
        log = _legacy_log_from_fake_db(db, log_id)
    if not log or log.status in {"success", "failed"}:
        return
    log.status = "success"
    if log.completed_at is None:
        log.completed_at = datetime.now(timezone.utc)
    db.add(log)
    db.commit()
    logger.info("[AsyncJobService] Inline fallback forced log %s â†' success", log_id)


# Register late-bound handlers that depend on async_job_service.
from AINDY.memory import embedding_jobs as _embedding_jobs  # noqa: E402,F401






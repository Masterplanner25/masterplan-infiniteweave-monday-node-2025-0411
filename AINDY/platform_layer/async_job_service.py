from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable
from uuid import UUID

from config import settings
from db.database import SessionLocal
from db.models.automation_log import AutomationLog
from db.models.system_event import SystemEvent
from core.execution_signal_helper import queue_system_event
from agents.autonomous_controller import build_decision_response
from agents.autonomous_controller import evaluate_live_trigger
from agents.autonomous_controller import record_decision
from core.execution_envelope import error as execution_error
from core.execution_envelope import success as execution_success
from core.system_event_service import emit_error_event
from core.system_event_types import SystemEventTypes
from utils.trace_context import get_parent_event_id
from utils.trace_context import reset_parent_event_id
from utils.trace_context import reset_trace_id
from utils.trace_context import set_parent_event_id
from utils.trace_context import set_trace_id
from utils.user_ids import parse_user_id

_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = Lock()
_JOB_REGISTRY: dict[str, Callable[[dict[str, Any], Any], Any]] = {}


def async_heavy_execution_enabled() -> bool:
    if os.getenv("TESTING", "false").lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("TEST_MODE", "false").lower() in {"1", "true", "yes"}:
        return False
    return os.getenv("AINDY_ASYNC_HEAVY_EXECUTION", "false").lower() in {"1", "true", "yes"}


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


def register_async_job(name: str):
    def _wrap(fn: Callable[[dict[str, Any], Any], Any]):
        _JOB_REGISTRY[name] = fn
        return fn
    return _wrap


def build_queued_response(log_id: str, *, task_name: str, source: str) -> dict[str, Any]:
    response = execution_success(
        result={
            "automation_log_id": log_id,
            "task_name": task_name,
            "source": source,
            "poll_url": f"/automation/logs/{log_id}",
        },
        events=[],
        trace_id=log_id,
        next_action={
            "type": "poll_automation_log",
            "automation_log_id": log_id,
        },
    )
    response["status"] = "QUEUED"
    return response


def build_deferred_response(
    log_id: str,
    *,
    task_name: str,
    source: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    response = build_decision_response(
        decision,
        trace_id=log_id,
        result={
            "automation_log_id": log_id,
            "task_name": task_name,
            "source": source,
            "poll_url": f"/automation/logs/{log_id}",
            "decision": decision.get("decision"),
            "priority": decision.get("priority"),
            "reason": decision.get("reason"),
        },
        next_action={
            "type": "retry_when_system_state_improves",
            "automation_log_id": log_id,
        },
    )
    response["status"] = "DEFERRED"
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


def _emit_async_system_event(*, db, event_type: str, user_id=None, trace_id: str | None = None, parent_event_id=None, source: str | None = None, payload: dict[str, Any] | None = None):
    from core.system_event_service import emit_system_event

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
    user_uuid = parse_user_id(user_id)
    db = SessionLocal()
    log_id = None
    try:
        log_id = str(uuid.uuid4())
        log = AutomationLog(
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
        db.refresh(log)
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
                "dispatch_state": "queued" if not settings.TEST_MODE else "inline",
            },
        )
        if settings.TEST_MODE and execute_inline_in_test_mode:
            _execute_job_inline(db, log_id, task_name, payload)
            return log_id
        if settings.TEST_MODE and not execute_inline_in_test_mode:
            return log_id
        if _session_dialect_name(db) == "sqlite" and task_name != "agent.create_run":
            _execute_job_inline(db, log_id, task_name, payload)
            return log_id
        future = _get_executor().submit(_execute_job, log_id, task_name, payload)
        if future.cancelled():
            raise RuntimeError(f"Async job '{task_name}' was cancelled before execution")
        return log_id
    except Exception as exc:
        if log_id is not None:
            try:
                log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()
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
    user_uuid = parse_user_id(user_id)
    db = SessionLocal()
    try:
        log_id = str(uuid.uuid4())
        delay_seconds = int(decision.get("defer_seconds") or 300)
        log = AutomationLog(
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
        db.refresh(log)
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
            automation_log_id=log_id,
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
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        trace_id = str(uuid.uuid4())
        context = dict(trigger_context or {})
        trigger = {
            "trigger_type": trigger_type,
            "source": source,
            "task_name": task_name,
            "goal": context.get("goal"),
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
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        logs = (
            db.query(AutomationLog)
            .filter(
                AutomationLog.status == "deferred",
                AutomationLog.scheduled_for.isnot(None),
                AutomationLog.scheduled_for <= now,
            )
            .order_by(AutomationLog.scheduled_for.asc())
            .limit(limit)
            .all()
        )
        resumed = 0
        for log in logs:
            autonomy = (log.payload or {}).get("__autonomy") or {}
            context = autonomy.get("context") or {}
            trigger = {
                "trigger_type": autonomy.get("trigger_type") or "system",
                "source": autonomy.get("source") or log.source,
                "task_name": log.task_name,
                "goal": context.get("goal"),
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
                automation_log_id=log.id,
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
                _get_executor().submit(_execute_job, log.id, log.task_name, log.payload or {})
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


def _execute_job_inline(db, log_id: str, task_name: str, payload: dict[str, Any]) -> None:
    trace_token = set_trace_id(str(log_id))
    parent_token = set_parent_event_id(_get_root_execution_event_id(db, str(log_id)))
    try:
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        if not log:
            return

        handler = _JOB_REGISTRY.get(task_name)
        if handler is None:
            raise RuntimeError(f"Async job handler '{task_name}' is not registered")
        queued_event_exists = _has_existing_execution_started(db, str(log_id))
        log.status = "running"
        log.started_at = datetime.now(timezone.utc)
        log.attempt_count += 1
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
            started_event_id = _emit_async_system_event(
                db=db,
                event_type=SystemEventTypes.EXECUTION_STARTED,
                user_id=log.user_id,
                trace_id=str(log_id),
                parent_event_id=get_parent_event_id(),
                source="async",
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                    "execution_mode": "async_job",
                    "dispatch_state": "direct",
                    "attempt_count": log.attempt_count,
                },
            )
        job_parent_token = set_parent_event_id(str(started_event_id) if started_event_id else get_parent_event_id())

        try:
            result = handler(payload, db)
            if not _is_execution_envelope(result):
                result = execution_success(result=result, events=[], trace_id=str(log_id))
        finally:
            reset_parent_event_id(job_parent_token)

        log.status = "success"
        log.result = _normalize_result(result)
        log.completed_at = datetime.now(timezone.utc)
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
        db.commit()
        db.refresh(log)
    except Exception as exc:
        db.rollback()
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        if log:
            failure_response = execution_error(str(exc), [], str(log_id))
            log.status = "failed"
            log.error_message = str(exc)
            log.result = _normalize_result(failure_response)
            log.completed_at = datetime.now(timezone.utc)
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
            db.refresh(log)
    finally:
        reset_parent_event_id(parent_token)
        reset_trace_id(trace_token)


def _execute_job(log_id: str, task_name: str, payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        _execute_job_inline(db, log_id, task_name, payload)
    finally:
        db.close()


_ANALYZER = None
_ANALYZER_LOCK = Lock()


def _get_analyzer():
    global _ANALYZER
    if _ANALYZER is None:
        with _ANALYZER_LOCK:
            if _ANALYZER is None:
                from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

                _ANALYZER = DeepSeekCodeAnalyzer()
    return _ANALYZER


@register_async_job("agent.create_run")
def _job_agent_create_run(payload: dict[str, Any], db):
    from agents.agent_runtime import create_run, execute_run, to_execution_response

    user_id = payload["user_id"]
    run = create_run(goal=payload["goal"], user_id=user_id, db=db)
    if not run:
        raise RuntimeError("Failed to generate plan")
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
    return to_execution_response(run, db)


@register_async_job("agent.approve_run")
def _job_agent_approve_run(payload: dict[str, Any], db):
    from agents.agent_runtime import approve_run, to_execution_response

    run = approve_run(run_id=payload["run_id"], user_id=payload["user_id"], db=db)
    if not run:
        raise RuntimeError("Run not found or not approvable")
    return to_execution_response(run, db)


@register_async_job("arm.analyze")
def _job_arm_analyze(payload: dict[str, Any], db):
    analyzer = _get_analyzer()
    return analyzer.run_analysis(
        file_path=payload["file_path"],
        user_id=payload["user_id"],
        db=db,
        complexity=payload.get("complexity"),
        urgency=payload.get("urgency"),
        additional_context=payload.get("context", ""),
    )


@register_async_job("arm.generate")
def _job_arm_generate(payload: dict[str, Any], db):
    analyzer = _get_analyzer()
    return analyzer.generate_code(
        prompt=payload["prompt"],
        user_id=payload["user_id"],
        db=db,
        original_code=payload.get("original_code", ""),
        language=payload.get("language", "python"),
        generation_type=payload.get("generation_type", "generate"),
        analysis_id=payload.get("analysis_id"),
        complexity=payload.get("complexity"),
        urgency=payload.get("urgency"),
    )


@register_async_job("genesis.message")
def _job_genesis_message(payload: dict[str, Any], db):
    from runtime.flow_engine import execute_intent

    return execute_intent(
        intent_data={
            "workflow_type": "genesis_message",
            "session_id": payload["session_id"],
            "message": payload["message"],
        },
        db=db,
        user_id=payload["user_id"],
    )


@register_async_job("genesis.synthesize")
def _job_genesis_synthesize(payload: dict[str, Any], db):
    from db.models import GenesisSessionDB
    from domain.genesis_ai import call_genesis_synthesis_llm

    user_id = UUID(str(payload["user_id"]))
    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == payload["session_id"], GenesisSessionDB.user_id == user_id)
        .first()
    )
    if not session:
        raise RuntimeError("GenesisSession not found")
    if not session.synthesis_ready:
        raise RuntimeError("Session is not ready for synthesis")

    draft = call_genesis_synthesis_llm(
        session.summarized_state or {},
        user_id=str(user_id),
        db=db,
    )
    session.draft_json = draft
    db.commit()
    return {"draft": draft}


@register_async_job("genesis.audit")
def _job_genesis_audit(payload: dict[str, Any], db):
    from db.models import GenesisSessionDB
    from domain.genesis_ai import validate_draft_integrity

    user_id = UUID(str(payload["user_id"]))
    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == payload["session_id"], GenesisSessionDB.user_id == user_id)
        .first()
    )
    if not session or not session.draft_json:
        raise RuntimeError("No draft available")
    return validate_draft_integrity(session.draft_json, user_id=str(user_id), db=db)


@register_async_job("memory.nodus.execute")
def _job_memory_nodus_execute(payload: dict[str, Any], db):
    from runtime.nodus_execution_service import execute_nodus_task_payload

    return execute_nodus_task_payload(
        task_name=payload["task_name"],
        task_code=payload["task_code"],
        db=db,
        user_id=payload["user_id"],
        session_tags=payload.get("session_tags"),
        allowed_operations=payload.get("allowed_operations"),
        execution_id=payload.get("execution_id"),
        capability_token=payload.get("capability_token"),
    )


@register_async_job("watcher.ingest")
def _job_watcher_ingest(payload: dict[str, Any], db):
    from runtime.flow_engine import execute_intent

    return execute_intent(
        intent_data={
            "workflow_type": "watcher_ingest",
            "signals": payload["signals"],
        },
        db=db,
        user_id=payload.get("user_id"),
    )


@register_async_job("automation.execute")
def _job_automation_execute(payload: dict[str, Any], db):
    from domain.automation_execution_service import execute_automation_action

    return execute_automation_action(payload, db)


@register_async_job("freelance.generate_delivery")
def _job_freelance_generate_delivery(payload: dict[str, Any], db):
    from domain.freelance_service import generate_deliverable

    return generate_deliverable(
        db=db,
        order_id=int(payload["order_id"]),
        user_id=payload.get("user_id"),
    )


# Register late-bound handlers that depend on async_job_service.
from memory import embedding_jobs as _embedding_jobs  # noqa: E402,F401




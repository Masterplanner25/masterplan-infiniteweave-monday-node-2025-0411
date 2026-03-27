from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import UUID

from db.database import SessionLocal
from db.models.automation_log import AutomationLog
from services.system_event_service import emit_error_event, emit_system_event
from utils.trace_context import reset_current_trace_id, set_current_trace_id
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
    return {
        "status": "QUEUED",
        "result": {
            "automation_log_id": log_id,
            "task_name": task_name,
            "source": source,
            "poll_url": f"/automation/logs/{log_id}",
        },
        "events": [],
        "next_action": {
            "type": "poll_automation_log",
            "automation_log_id": log_id,
        },
        "trace_id": log_id,
    }


def submit_async_job(
    *,
    task_name: str,
    payload: dict[str, Any],
    user_id: str | UUID | None,
    source: str,
    max_attempts: int = 1,
) -> str:
    user_uuid = parse_user_id(user_id)
    db = SessionLocal()
    try:
        log = AutomationLog(
            source=source,
            task_name=task_name,
            payload=payload,
            status="pending",
            max_attempts=max_attempts,
            user_id=user_uuid,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        log_id = log.id
    finally:
        db.close()

    _get_executor().submit(_execute_job, log_id, task_name, payload)
    return log_id


def _normalize_result(result: Any) -> Any:
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return result
    return {"result": str(result)}


def _execute_job(log_id: str, task_name: str, payload: dict[str, Any]) -> None:
    db = SessionLocal()
    trace_token = set_current_trace_id(str(log_id))
    try:
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        if not log:
            return

        handler = _JOB_REGISTRY[task_name]
        log.status = "running"
        log.started_at = datetime.now(timezone.utc)
        log.attempt_count += 1
        db.commit()
        emit_system_event(
            db=db,
            event_type="execution.started",
            user_id=log.user_id,
            trace_id=str(log_id),
            payload={
                "run_id": str(log_id),
                "task_name": task_name,
                "source": log.source,
                "execution_mode": "async_job",
            },
            required=True,
        )

        result = handler(payload, db)

        log.status = "success"
        log.result = _normalize_result(result)
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        emit_system_event(
            db=db,
            event_type="execution.completed",
            user_id=log.user_id,
            trace_id=str(log_id),
            payload={
                "run_id": str(log_id),
                "task_name": task_name,
                "source": log.source,
                "execution_mode": "async_job",
                "result": _normalize_result(result),
            },
            required=True,
        )
    except Exception as exc:
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        if log:
            log.status = "failed"
            log.error_message = str(exc)
            log.completed_at = datetime.now(timezone.utc)
            db.commit()
            emit_system_event(
                db=db,
                event_type="execution.failed",
                user_id=log.user_id,
                trace_id=str(log_id),
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                    "execution_mode": "async_job",
                    "error": str(exc),
                },
                required=True,
            )
            emit_error_event(
                db=db,
                error_type="async_job_execution",
                message=str(exc),
                user_id=log.user_id,
                trace_id=str(log_id),
                payload={
                    "run_id": str(log_id),
                    "task_name": task_name,
                    "source": log.source,
                },
                required=True,
            )
    finally:
        reset_current_trace_id(trace_token)
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
    from services.agent_runtime import create_run, execute_run, to_execution_response

    user_id = payload["user_id"]
    run = create_run(goal=payload["goal"], user_id=user_id, db=db)
    if not run:
        raise RuntimeError("Failed to generate plan")
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
    return to_execution_response(run, db)


@register_async_job("agent.approve_run")
def _job_agent_approve_run(payload: dict[str, Any], db):
    from services.agent_runtime import approve_run, to_execution_response

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
    from services.flow_engine import execute_intent

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
    from services.genesis_ai import call_genesis_synthesis_llm

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
    from services.genesis_ai import validate_draft_integrity

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
    from services.nodus_execution_service import execute_nodus_task_payload

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

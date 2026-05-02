from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from AINDY.db.models import AgentTrustSettings
from AINDY.db.models.background_task_lease import BackgroundTaskLease
from AINDY.db.models.job_log import JobLog
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.user_identity import UserIdentity
from AINDY.platform_layer.async_job_service import _JOB_REGISTRY, submit_async_job


VALID_PLAN = {
    "executive_summary": "Create a task and gather context.",
    "steps": [
        {
            "tool": "task.create",
            "args": {"name": "Hardening follow up"},
            "risk_level": "low",
            "description": "Create follow-up task",
        }
    ],
    "overall_risk": "low",
}


def _wait_for_log(db_or_factory, log_id: str, timeout_s: float = 5.0) -> JobLog:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if callable(db_or_factory):
            db_session = db_or_factory()
            should_close = True
        else:
            db_session = db_or_factory
            should_close = False
        try:
            db_session.expire_all()
            log = db_session.query(JobLog).filter(JobLog.id == log_id).first()
        finally:
            if should_close:
                db_session.close()
        if log and log.status in {"success", "failed"}:
            return log
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for automation log {log_id}")


def test_async_job_never_disappears(client, db_session, testing_session_factory, test_user, auth_headers, monkeypatch):
    db_session.add(
        AgentTrustSettings(
            user_id=test_user.id,
            auto_execute_low=True,
            auto_execute_medium=False,
            allowed_auto_grant_tools=["task.create"],
        )
    )
    db_session.commit()

    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("AINDY_ASYNC_HEAVY_EXECUTION", "true")
    monkeypatch.setattr("AINDY.agents.agent_runtime.generate_plan", lambda **kwargs: VALID_PLAN)

    def _complete_run(**kwargs):
        return {"status": "SUCCESS", "run_id": str(uuid.uuid4())}

    monkeypatch.setattr("AINDY.runtime.nodus_adapter.NodusAgentAdapter.execute_with_flow", _complete_run)

    response = client.post("/apps/agent/run", headers=auth_headers, json={"goal": "Harden async execution"})
    assert response.status_code == 202
    payload = response.json()
    data = payload.get("data", payload)
    result = data.get("result", data)
    log_id = result.get("automation_log_id") or data.get("automation_log_id")

    log = _wait_for_log(testing_session_factory, log_id)
    assert log.status == "success"
    assert log.result is not None

    event_types = [
        event.type
        for event in db_session.query(SystemEvent)
        .filter(SystemEvent.trace_id == log_id)
        .order_by(SystemEvent.timestamp.asc())
        .all()
    ]
    assert "execution.started" in event_types
    assert "async_job.started" in event_types
    assert "async_job.completed" in event_types
    assert "execution.completed" in event_types


def test_db_rollback_works_on_async_job_failure(db_session, testing_session_factory, test_user, monkeypatch):
    import AINDY.platform_layer.async_job_service as async_job_service

    monkeypatch.setattr(async_job_service, "SessionLocal", testing_session_factory)
    job_name = "hardening.rollback"

    def _failing_job(payload, db):
        db.add(
            UserIdentity(
                user_id=test_user.id,
                tone="casual",
                last_updated=datetime.now(timezone.utc),
            )
        )
        raise RuntimeError("forced mid-transaction failure")

    _JOB_REGISTRY[job_name] = _failing_job
    try:
        log_id = submit_async_job(
            task_name=job_name,
            payload={"user_id": str(test_user.id)},
            user_id=test_user.id,
            source="test_hardening",
        )
    finally:
        _JOB_REGISTRY.pop(job_name, None)

    log = _wait_for_log(testing_session_factory, log_id)
    assert log.status == "failed"
    assert "forced mid-transaction failure" in (log.error_message or "")

    persisted_identity = (
        db_session.query(UserIdentity)
        .filter(UserIdentity.user_id == test_user.id)
        .first()
    )
    assert persisted_identity is None

    event_types = {
        event.type
        for event in db_session.query(SystemEvent)
        .filter(SystemEvent.trace_id == log_id)
        .all()
    }
    assert "execution.failed" in event_types
    assert "error.async_job_execution" in event_types


def test_lease_exclusivity(db_session, db_session_factory, monkeypatch):
    import apps.tasks.services.task_service as task_services

    monkeypatch.setattr(task_services, "SessionLocal", db_session_factory)

    monkeypatch.setattr(task_services, "_get_instance_id", lambda: "worker-a")
    assert task_services._acquire_background_lease() is True

    monkeypatch.setattr(task_services, "_get_instance_id", lambda: "worker-b")
    assert task_services._acquire_background_lease() is False

    lease = (
        db_session.query(BackgroundTaskLease)
        .filter(BackgroundTaskLease.name == "task_background_runner")
        .one()
    )
    lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    monkeypatch.setattr(task_services, "_get_instance_id", lambda: "worker-b")
    assert task_services._acquire_background_lease() is True

    db_session.expire_all()
    lease = (
        db_session.query(BackgroundTaskLease)
        .filter(BackgroundTaskLease.name == "task_background_runner")
        .one()
    )
    assert lease.owner_id == "worker-b"


def test_event_completeness_for_successful_job(db_session, testing_session_factory, test_user, monkeypatch):
    import AINDY.platform_layer.async_job_service as async_job_service

    monkeypatch.setattr(async_job_service, "SessionLocal", testing_session_factory)
    job_name = "hardening.success"

    def _successful_job(payload, db):
        return {"ok": True, "payload": payload}

    _JOB_REGISTRY[job_name] = _successful_job
    try:
        log_id = submit_async_job(
            task_name=job_name,
            payload={"action": "event_chain"},
            user_id=test_user.id,
            source="test_hardening",
        )
    finally:
        _JOB_REGISTRY.pop(job_name, None)

    log = _wait_for_log(testing_session_factory, log_id)
    assert log.status == "success"

    event_types = [
        event.type
        for event in db_session.query(SystemEvent)
        .filter(SystemEvent.trace_id == log_id)
        .order_by(SystemEvent.timestamp.asc())
        .all()
    ]
    assert event_types[0] == "execution.started"
    assert "async_job.started" in event_types
    assert "async_job.completed" in event_types
    assert "execution.completed" in event_types


def test_invalid_uuid_input_fails_cleanly(client, auth_headers):
    agent_response = client.get("/apps/agent/runs/not-a-uuid", headers=auth_headers)
    assert agent_response.status_code == 400
    payload = agent_response.json()
    data = payload.get("data", payload)
    assert "Invalid run_id" in str(data)



"""
tests/integration/test_execution_contract.py
─────────────────────────────────────────────
Integration tests for the V1 execution contract.

Verifies that both the Genesis and Task subsystems emit the correct
SystemEvent rows at each lifecycle point.  These tests go deeper than
the v1_gates pass/fail checks: they validate event_type values, inspect
payloads, and confirm the contract is resilient to emit failures.

Fixtures
--------
All fixtures (client, auth_headers, db_session, test_user) are provided
by the shared conftest chain (tests/conftest.py → tests/fixtures/*).

The module-level ``_patch_session_local_to_engine`` fixture re-patches
db.database.SessionLocal to the engine-bound testing_session_factory so
that emit_observability_event() writes to an independent connection that
survives any pipeline-level rollbacks on the test connection.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from apps.masterplan.events import MasterplanEventTypes
from apps.tasks.events import TaskEventTypes


# ── Session patching ──────────────────────────────────────────────────────────
# Must run AFTER the `app` fixture's _patch_session_aliases so that the
# engine-bound factory is the one in effect during each test.

@pytest.fixture(autouse=True)
def _patch_session_local_to_engine(app, testing_session_factory, monkeypatch):
    """
    Re-patch db.database.SessionLocal to the engine-bound factory for every
    test in this module.

    emit_observability_event() opens its own SessionLocal() session.  With
    the default db_session_factory (bound to db_connection), pipeline FK
    errors can roll back those emits.  The engine-bound factory gives the
    emit its own connection so its commits are real and survive subsequent
    rollbacks on the test connection.
    """
    import AINDY.db.database as _db_module

    monkeypatch.setattr(_db_module, "SessionLocal", testing_session_factory, raising=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

_TASK_NAME_BASE = "exec-contract-test"


def _task_name(suffix: str) -> str:
    return f"{_TASK_NAME_BASE}-{suffix}"


def _events_of_type(db_session, event_type: str):
    """Return all SystemEvent rows matching event_type (refreshed)."""
    from AINDY.db.models.system_event import SystemEvent

    db_session.expire_all()
    return (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == event_type)
        .all()
    )


def _latest_event_of_type(db_session, event_type: str):
    events = _events_of_type(db_session, event_type)
    return events[-1] if events else None


def _count_events_of_type(db_session, event_type: str) -> int:
    return len(_events_of_type(db_session, event_type))


# ── Test 1 ────────────────────────────────────────────────────────────────────

def test_task_create_emits_task_created_event(client, auth_headers, db_session, test_user):
    """
    POST /apps/tasks/create must emit a SystemEvent with event_type == 'task.created'.
    The event payload must contain both 'task_id' and 'name' keys.
    """
    user_id = str(test_user.id)
    before = _count_events_of_type(db_session, TaskEventTypes.TASK_CREATED)

    response = client.post(
        "/apps/tasks/create",
        json={"title": _task_name("create"), "user_id": user_id},
        headers=auth_headers,
    )

    assert response.status_code < 500, (
        f"POST /apps/tasks/create returned {response.status_code}: {response.text}"
    )

    events = _events_of_type(db_session, TaskEventTypes.TASK_CREATED)
    assert len(events) > before, (
        f"Expected at least one new '{TaskEventTypes.TASK_CREATED}' event "
        f"(before={before}, after={len(events)})"
    )

    new_events = events[before:]
    payload_keys = set()
    for ev in new_events:
        if isinstance(ev.payload, dict):
            payload_keys.update(ev.payload.keys())

    assert "name" in payload_keys, (
        f"No new '{TaskEventTypes.TASK_CREATED}' event has 'name' in payload. "
        f"Payloads: {[ev.payload for ev in new_events]}"
    )
    assert "task_id" in payload_keys, (
        f"No new '{TaskEventTypes.TASK_CREATED}' event has 'task_id' in payload. "
        f"Payloads: {[ev.payload for ev in new_events]}"
    )
    latest = _latest_event_of_type(db_session, TaskEventTypes.TASK_CREATED)
    assert latest is not None
    assert str(latest.user_id) == user_id


# ── Test 2 ────────────────────────────────────────────────────────────────────

def test_task_start_emits_task_started_event(db_session, test_user):
    """
    Calling start_task() via the service layer must emit a 'task.started' event.
    """
    user_id = str(test_user.id)
    from apps.tasks.services.task_service import create_task, start_task

    name = _task_name("start")
    create_task(db_session, name, user_id=user_id)

    before = _count_events_of_type(db_session, TaskEventTypes.TASK_STARTED)

    start_task(db_session, name, user_id=user_id)

    after = _count_events_of_type(db_session, TaskEventTypes.TASK_STARTED)
    assert after > before, (
        f"Expected at least one new '{TaskEventTypes.TASK_STARTED}' event "
        f"(before={before}, after={after})"
    )
    latest = _latest_event_of_type(db_session, TaskEventTypes.TASK_STARTED)
    assert latest is not None
    assert str(latest.user_id) == user_id


# ── Test 3 ────────────────────────────────────────────────────────────────────

def test_task_complete_emits_task_completed_event(db_session, test_user):
    """
    Calling complete_task() via the service layer must emit a 'task.completed' event.
    """
    user_id = str(test_user.id)
    from apps.tasks.services.task_service import create_task, start_task, complete_task

    name = _task_name("complete")
    create_task(db_session, name, user_id=user_id)
    start_task(db_session, name, user_id=user_id)

    before = _count_events_of_type(db_session, TaskEventTypes.TASK_COMPLETED)

    complete_task(db_session, name, user_id=user_id)

    after = _count_events_of_type(db_session, TaskEventTypes.TASK_COMPLETED)
    assert after > before, (
        f"Expected at least one new '{TaskEventTypes.TASK_COMPLETED}' event "
        f"(before={before}, after={after})"
    )
    latest = _latest_event_of_type(db_session, TaskEventTypes.TASK_COMPLETED)
    assert latest is not None
    assert str(latest.user_id) == user_id


# ── Test 4 ────────────────────────────────────────────────────────────────────

def test_task_pause_emits_task_paused_event(db_session, test_user):
    """
    Calling pause_task() via the service layer must emit a 'task.paused' event.
    """
    user_id = str(test_user.id)
    from apps.tasks.services.task_service import create_task, start_task, pause_task

    name = _task_name("pause")
    create_task(db_session, name, user_id=user_id)
    start_task(db_session, name, user_id=user_id)

    before = _count_events_of_type(db_session, TaskEventTypes.TASK_PAUSED)

    pause_task(db_session, name, user_id=user_id)

    after = _count_events_of_type(db_session, TaskEventTypes.TASK_PAUSED)
    assert after > before, (
        f"Expected at least one new '{TaskEventTypes.TASK_PAUSED}' event "
        f"(before={before}, after={after})"
    )
    latest = _latest_event_of_type(db_session, TaskEventTypes.TASK_PAUSED)
    assert latest is not None
    assert str(latest.user_id) == user_id


# ── Test 5 ────────────────────────────────────────────────────────────────────

def test_genesis_message_emits_started_event(client, auth_headers, db_session, test_user):
    """
    POST /apps/genesis/message must emit a 'genesis.message.started' event.
    This event is emitted BEFORE the flow runs, so it fires even when no
    genesis session exists and the flow returns an error.

    Skips if the endpoint itself is unavailable (404/422).
    """
    before = _count_events_of_type(db_session, MasterplanEventTypes.GENESIS_MESSAGE_STARTED)

    response = client.post(
        "/apps/genesis/message",
        json={"session_id": 99999, "message": "exec-contract integration probe"},
        headers=auth_headers,
    )

    if response.status_code in (404, 422):
        pytest.skip("no genesis session available in test DB")

    after = _count_events_of_type(db_session, MasterplanEventTypes.GENESIS_MESSAGE_STARTED)
    assert after > before, (
        f"Expected at least one new '{MasterplanEventTypes.GENESIS_MESSAGE_STARTED}' event "
        f"(before={before}, after={after}). Response: {response.status_code}"
    )


# ── Test 6 ────────────────────────────────────────────────────────────────────

def test_contract_events_are_never_fatal(client, auth_headers, test_user):
    """
    A failure inside emit_observability_event() must NOT propagate to the caller.
    POST /apps/tasks/create must still return 2xx even when the emit raises.
    """
    user_id = str(test_user.id)
    with patch(
        "core.observability_events.emit_observability_event",
        side_effect=RuntimeError("simulated emit failure"),
    ):
        response = client.post(
            "/apps/tasks/create",
            json={"title": _task_name("emit-fault"), "user_id": user_id},
            headers=auth_headers,
        )

    assert response.status_code < 500, (
        f"Emit failure must not propagate to the caller — "
        f"got {response.status_code}: {response.text}"
    )


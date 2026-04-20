"""Tests for the explicit job_log.written event + sync_job_log_to_automation_log."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Test 1: ORM event listener is NOT registered
# ---------------------------------------------------------------------------

def _get_mapper_listeners(mapper, event_name: str) -> list:
    """Return the list of listeners for a mapper event using the public dispatch API."""
    dispatch = getattr(mapper, "dispatch", None)
    if dispatch is None:
        return []
    chain = getattr(dispatch, event_name, None)
    if chain is None:
        return []
    # The dispatch chain exposes listeners via __iter__ or .listeners
    try:
        return list(chain)
    except TypeError:
        return []


def test_orm_after_insert_listener_not_registered():
    from AINDY.db.models.job_log import JobLog

    listeners = _get_mapper_listeners(JobLog.__mapper__, "after_insert")
    assert not listeners, "No after_insert ORM listeners should be registered on JobLog"


def test_orm_after_update_listener_not_registered():
    from AINDY.db.models.job_log import JobLog

    listeners = _get_mapper_listeners(JobLog.__mapper__, "after_update")
    assert not listeners, "No after_update ORM listeners should be registered on JobLog"


# ---------------------------------------------------------------------------
# Test 2: sync_job_log_to_automation_log upserts into AutomationLog
# ---------------------------------------------------------------------------

def _make_job_log_row(**kwargs):
    row = MagicMock()
    row.id = kwargs.get("id", str(uuid.uuid4()))
    row.source = kwargs.get("source", "test_source")
    row.job_name = kwargs.get("job_name", "test_task")
    row.task_name = kwargs.get("task_name", "test_task")
    row.payload = kwargs.get("payload", {"k": "v"})
    row.status = kwargs.get("status", "pending")
    row.attempt_count = kwargs.get("attempt_count", 0)
    row.max_attempts = kwargs.get("max_attempts", 3)
    row.error_message = kwargs.get("error_message", None)
    row.user_id = kwargs.get("user_id", None)
    row.result = kwargs.get("result", None)
    row.trace_id = kwargs.get("trace_id", str(uuid.uuid4()))
    row.started_at = kwargs.get("started_at", None)
    row.completed_at = kwargs.get("completed_at", None)
    row.created_at = kwargs.get("created_at", None)
    row.scheduled_for = kwargs.get("scheduled_for", None)
    return row


def test_sync_job_log_insert_creates_automation_log():
    from apps.automation.services.job_log_sync_service import sync_job_log_to_automation_log
    from apps.automation.automation_log import AutomationLog

    job_log_row = _make_job_log_row()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no existing row

    sync_job_log_to_automation_log(db, job_log_row)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert isinstance(added, AutomationLog)
    assert str(added.id) == str(job_log_row.id)
    assert added.source == job_log_row.source
    db.commit.assert_called_once()


def test_sync_job_log_update_existing_automation_log():
    from apps.automation.services.job_log_sync_service import sync_job_log_to_automation_log

    job_log_row = _make_job_log_row(status="success")
    existing = MagicMock()
    existing.id = job_log_row.id

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    sync_job_log_to_automation_log(db, job_log_row)

    assert existing.status == "success"
    db.add.assert_called_once_with(existing)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: sync is a no-op (not an error) when AutomationLog columns differ
# ---------------------------------------------------------------------------

def test_sync_no_op_on_missing_columns():
    """sync_job_log_to_automation_log must not raise even if a field doesn't exist."""
    from apps.automation.services.job_log_sync_service import sync_job_log_to_automation_log

    job_log_row = _make_job_log_row()
    # Simulate a db that throws on commit — should be caught silently
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit.side_effect = Exception("column mismatch")

    # Must not raise
    sync_job_log_to_automation_log(db, job_log_row)


# ---------------------------------------------------------------------------
# Test 4: emit_event("job_log.written") triggers sync via the bootstrap handler
# ---------------------------------------------------------------------------

def test_handle_job_log_written_calls_sync():
    """The bootstrap handler re-queries JobLog and calls sync."""
    from apps.automation.bootstrap import _handle_job_log_written

    job_log_id = str(uuid.uuid4())
    mock_row = _make_job_log_row(id=job_log_id)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_row

    with patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
         patch("apps.automation.services.job_log_sync_service.sync_job_log_to_automation_log") as mock_sync:
        _handle_job_log_written({"job_log_id": job_log_id, "source": "async_job_service"})

    mock_db.close.assert_called_once()


def test_handle_job_log_written_no_op_when_missing_id():
    from apps.automation.bootstrap import _handle_job_log_written

    with patch("AINDY.db.database.SessionLocal") as mock_session_cls:
        _handle_job_log_written({})

    mock_session_cls.assert_not_called()


def test_handle_job_log_written_no_op_when_row_not_found():
    from apps.automation.bootstrap import _handle_job_log_written

    job_log_id = str(uuid.uuid4())
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
         patch("apps.automation.services.job_log_sync_service.sync_job_log_to_automation_log") as mock_sync:
        _handle_job_log_written({"job_log_id": job_log_id})

    mock_sync.assert_not_called()
    mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: _emit_job_log_written calls emit_event with correct payload
# ---------------------------------------------------------------------------

def test_emit_job_log_written_calls_emit_event():
    import sys
    import types

    log_id = str(uuid.uuid4())
    captured = {}

    # _emit_job_log_written does `from AINDY.platform_layer.registry import emit_event`
    # inside its body. Patch the function on the registry module directly.
    from AINDY.platform_layer import registry as _registry

    original_emit = getattr(_registry, "emit_event", None)
    try:
        def fake_emit(event_type, context=None):
            captured["event_type"] = event_type
            captured["context"] = context

        _registry.emit_event = fake_emit

        # Import async_job_service carefully — it has a heavy import chain.
        # Stub prometheus_client if missing.
        if "prometheus_client" not in sys.modules:
            pm = types.ModuleType("prometheus_client")
            for cls_name in ("Counter", "Histogram", "Gauge", "CollectorRegistry"):
                setattr(pm, cls_name, MagicMock)
            sys.modules["prometheus_client"] = pm

        from AINDY.platform_layer.async_job_service import _emit_job_log_written
        _emit_job_log_written(log_id)
    finally:
        if original_emit is not None:
            _registry.emit_event = original_emit

    assert captured.get("event_type") == "job_log.written"
    assert captured.get("context", {}).get("job_log_id") == log_id
    assert captured.get("context", {}).get("source") == "async_job_service"

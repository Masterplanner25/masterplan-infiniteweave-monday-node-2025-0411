from __future__ import annotations

import uuid
from unittest.mock import patch


def test_emit_system_event_persists_to_test_db(db_session, test_user):
    from AINDY.db.models.system_event import SystemEvent
    from AINDY.core.execution_signal_helper import queue_system_event
    from AINDY.platform_layer.trace_context import reset_pipeline_active, set_pipeline_active

    trace_id = str(uuid.uuid4())
    token = set_pipeline_active(True)
    try:
        queue_system_event(
            db=db_session,
            event_type="execution.started",
            user_id=test_user.id,
            trace_id=trace_id,
            payload={"status": "started"},
            required=True,
        )
    finally:
        reset_pipeline_active(token)

    rows = db_session.query(SystemEvent).filter(SystemEvent.type == "execution.started").all()
    assert len(rows) == 1
    assert rows[0].type == "execution.started"
    assert rows[0].trace_id == trace_id


def test_emit_system_event_notifies_scheduler(db_session, test_user):
    """emit_system_event() calls _notify_scheduler_of_event after persistence."""
    from AINDY.core.system_event_service import emit_system_event

    with patch(
        "AINDY.core.system_event_service._notify_scheduler_of_event"
    ) as mock_notify:
        emit_system_event(
            db=db_session,
            event_type="task.completed",
            user_id=test_user.id,
            trace_id="trace-abc",
            payload={"result": "ok"},
        )

    mock_notify.assert_called_once_with(
        "task.completed",
        trace_id="trace-abc",
        payload={"result": "ok"},
    )


def test_notify_scheduler_wakes_waiting_run(db_session, test_user):
    """End-to-end: emit → notify_event → run enqueued in scheduler."""
    from AINDY.kernel.scheduler_engine import SchedulerEngine
    from AINDY.core.wait_condition import WaitCondition
    from AINDY.core.system_event_service import emit_system_event

    se = SchedulerEngine()
    se.mark_rehydration_complete()
    wc = WaitCondition.for_event("task.completed")
    resumed_flag = []

    se.register_wait(
        run_id="run-e2e",
        wait_for_event="task.completed",
        tenant_id=str(test_user.id),
        eu_id="eu-e2e",
        resume_callback=lambda: resumed_flag.append(True),
        wait_condition=wc,
    )

    with patch(
        "AINDY.core.system_event_service._notify_scheduler_of_event",
        side_effect=lambda et, **kw: se.notify_event(et, correlation_id=kw.get("trace_id")),
    ):
        emit_system_event(
            db=db_session,
            event_type="task.completed",
            user_id=test_user.id,
            trace_id="trace-xyz",
        )

    assert se.queue_depth()["normal"] == 1
    assert se.waiting_for("run-e2e") is None

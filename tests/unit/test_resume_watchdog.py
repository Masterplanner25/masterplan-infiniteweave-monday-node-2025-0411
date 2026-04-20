from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.waiting_flow_run import WaitingFlowRun


def _seed_waiting_flow(
    db_session,
    *,
    run_id: str,
    status: str = "waiting",
    event_type: str = "task.completed",
    correlation_id: str | None = "trace-watchdog",
    waited_since=None,
):
    now = datetime.now(timezone.utc)
    flow_run = FlowRun(
        id=run_id,
        flow_name="test.flow",
        workflow_type="test_flow",
        state={},
        current_node="wait_node",
        status=status,
        waiting_for=event_type,
        wait_deadline=now + timedelta(minutes=5),
        trace_id=correlation_id,
    )
    waiting_row = WaitingFlowRun(
        run_id=run_id,
        event_type=event_type,
        correlation_id=correlation_id,
        waited_since=waited_since or (now - timedelta(minutes=5)),
        max_wait_seconds=None,
        timeout_at=now + timedelta(minutes=5),
        eu_id=f"eu-{run_id}",
        priority="normal",
        instance_id="test",
    )
    db_session.add(flow_run)
    db_session.add(waiting_row)
    db_session.commit()
    return flow_run, waiting_row


def test_scan_finds_no_stranded_flows_when_waiting_is_empty(db_session):
    from AINDY.core.resume_watchdog import scan_and_resume_stranded_flows

    count = scan_and_resume_stranded_flows(db_session)

    assert count == 0


def test_scan_skips_flow_run_not_in_waiting_status(db_session):
    from AINDY.core.resume_watchdog import scan_and_resume_stranded_flows

    _seed_waiting_flow(db_session, run_id="completed-run", status="completed")

    with patch("AINDY.core.resume_watchdog.get_scheduler_engine", create=True) as _unused:
        count = scan_and_resume_stranded_flows(db_session)

    assert count == 0


def test_scan_skips_flow_with_no_matching_system_event(db_session):
    from AINDY.core.resume_watchdog import scan_and_resume_stranded_flows

    _seed_waiting_flow(db_session, run_id="no-event-run")
    scheduler = MagicMock()
    scheduler.waiting_for.return_value = "task.completed"
    scheduler.notify_event.return_value = 0

    with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=scheduler):
        count = scan_and_resume_stranded_flows(db_session)

    assert count == 0
    scheduler.notify_event.assert_not_called()


def test_scan_resumes_when_matching_system_event_exists(db_session):
    from AINDY.core.resume_watchdog import scan_and_resume_stranded_flows

    _, waiting_row = _seed_waiting_flow(
        db_session,
        run_id="resume-run",
        event_type="task.completed",
        correlation_id="trace-resume-run",
        waited_since=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(
        SystemEvent(
            type="task.completed",
            trace_id="trace-resume-run",
            source="test",
            payload={},
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    scheduler = MagicMock()
    scheduler.waiting_for.return_value = waiting_row.event_type
    scheduler.notify_event.return_value = 1

    with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=scheduler):
        count = scan_and_resume_stranded_flows(db_session)

    assert count == 1
    scheduler.notify_event.assert_called_once_with(
        "task.completed",
        correlation_id="trace-resume-run",
        broadcast=False,
    )


def test_scan_reregisters_missing_callback_before_resume(db_session):
    from AINDY.core.resume_watchdog import scan_and_resume_stranded_flows

    _seed_waiting_flow(
        db_session,
        run_id="rehydrate-run",
        event_type="task.completed",
        correlation_id="trace-rehydrate-run",
        waited_since=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(
        SystemEvent(
            type="task.completed",
            trace_id="trace-rehydrate-run",
            source="test",
            payload={},
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    scheduler = MagicMock()
    scheduler.waiting_for.side_effect = [None]
    scheduler.notify_event.return_value = 1

    with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=scheduler), \
         patch("AINDY.core.resume_watchdog.rehydrate_waiting_flow_runs", create=True) as _unused, \
         patch("AINDY.core.flow_run_rehydration.rehydrate_waiting_flow_runs") as mock_rehydrate:
        count = scan_and_resume_stranded_flows(db_session)

    assert count == 1
    mock_rehydrate.assert_called_once_with(db_session)


def test_watchdog_registered_as_scheduled_job():
    import apps.bootstrap
    from AINDY.platform_layer.registry import get_scheduled_jobs, iter_jobs

    apps.bootstrap.bootstrap()
    job_ids = {job["id"] for job in get_scheduled_jobs()}
    sync_job_names = {name for name, _handler in iter_jobs()}

    assert "resume_watchdog" in job_ids
    assert "resume_watchdog.scan" in sync_job_names

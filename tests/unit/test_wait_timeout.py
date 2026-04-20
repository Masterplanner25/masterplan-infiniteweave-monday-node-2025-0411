from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.waiting_flow_run import WaitingFlowRun
from AINDY.platform_layer.recovery_jobs import expire_timed_out_wait_flows


def _seed_waiting_flow(
    db_session,
    *,
    run_id: str,
    max_wait_seconds: int | None,
    waited_since: datetime,
    status: str = "waiting",
) -> tuple[FlowRun, WaitingFlowRun]:
    flow_run = FlowRun(
        id=run_id,
        flow_name="test.flow",
        workflow_type="test_flow",
        state={},
        current_node="wait_node",
        status=status,
        waiting_for="approval.received",
        wait_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        trace_id=f"trace-{run_id}",
    )
    waiting_row = WaitingFlowRun(
        run_id=run_id,
        event_type="approval.received",
        correlation_id=f"trace-{run_id}",
        waited_since=waited_since,
        max_wait_seconds=max_wait_seconds,
        timeout_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        eu_id=f"eu-{run_id}",
        priority="normal",
        instance_id="test",
    )
    db_session.add(flow_run)
    db_session.add(waiting_row)
    db_session.commit()
    db_session.refresh(flow_run)
    db_session.refresh(waiting_row)
    return flow_run, waiting_row


def test_no_timeout_when_max_wait_seconds_is_none(db_session):
    flow_run, waiting_row = _seed_waiting_flow(
        db_session,
        run_id="wait-none",
        max_wait_seconds=None,
        waited_since=datetime.now(timezone.utc) - timedelta(days=1),
    )

    count = asyncio.run(expire_timed_out_wait_flows(db_session))

    db_session.refresh(flow_run)
    db_session.refresh(waiting_row)
    assert count == 0
    assert flow_run.status == "waiting"
    assert flow_run.error_detail is None
    assert (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "WAIT_TIMEOUT")
        .count()
        == 0
    )


def test_not_expired_before_deadline(db_session):
    flow_run, waiting_row = _seed_waiting_flow(
        db_session,
        run_id="wait-before",
        max_wait_seconds=300,
        waited_since=datetime.now(timezone.utc) - timedelta(seconds=100),
    )

    count = asyncio.run(expire_timed_out_wait_flows(db_session))

    db_session.refresh(flow_run)
    db_session.refresh(waiting_row)
    assert count == 0
    assert flow_run.status == "waiting"
    assert flow_run.error_detail is None
    assert (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "WAIT_TIMEOUT")
        .count()
        == 0
    )


def test_expired_after_deadline(db_session):
    flow_run, _ = _seed_waiting_flow(
        db_session,
        run_id="wait-expired",
        max_wait_seconds=300,
        waited_since=datetime.now(timezone.utc) - timedelta(seconds=400),
    )

    count = asyncio.run(expire_timed_out_wait_flows(db_session))

    db_session.refresh(flow_run)
    event = (
        db_session.query(SystemEvent)
        .filter(
            SystemEvent.type == "WAIT_TIMEOUT",
            SystemEvent.trace_id == "trace-wait-expired",
        )
        .one()
    )
    deleted_row = (
        db_session.query(WaitingFlowRun)
        .filter(WaitingFlowRun.run_id == "wait-expired")
        .first()
    )

    assert count == 1
    assert flow_run.status == "failed"
    assert flow_run.error_message == "WAIT_TIMEOUT"
    assert flow_run.error_detail["reason"] == "wait_timeout"
    assert flow_run.error_detail["elapsed_seconds"] > 300
    assert deleted_row is None
    assert event.payload["flow_run_id"] == "wait-expired"
    assert event.payload["elapsed_seconds"] > 300


def test_returns_count_of_expired_flows(db_session):
    now = datetime.now(timezone.utc)
    for idx in range(3):
        _seed_waiting_flow(
            db_session,
            run_id=f"expired-{idx}",
            max_wait_seconds=300,
            waited_since=now - timedelta(seconds=400 + idx),
        )
    for idx in range(2):
        _seed_waiting_flow(
            db_session,
            run_id=f"active-{idx}",
            max_wait_seconds=300,
            waited_since=now - timedelta(seconds=100 + idx),
        )

    count = asyncio.run(expire_timed_out_wait_flows(db_session))

    failed_runs = (
        db_session.query(FlowRun)
        .filter(FlowRun.status == "failed")
        .count()
    )
    remaining_wait_rows = db_session.query(WaitingFlowRun).count()
    timeout_events = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "WAIT_TIMEOUT")
        .count()
    )

    assert count == 3
    assert failed_runs == 3
    assert remaining_wait_rows == 2
    assert timeout_events == 3

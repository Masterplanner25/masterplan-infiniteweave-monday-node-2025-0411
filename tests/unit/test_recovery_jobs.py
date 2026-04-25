from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from AINDY.config import settings
from AINDY.db.models.flow_run import FlowRun
from AINDY.platform_layer.recovery_jobs import (
    expire_timed_out_waits,
    recover_stuck_runs,
)


def _seed_flow_run(
    db_session,
    *,
    status: str,
    wait_deadline: datetime | None = None,
    updated_at: datetime | None = None,
) -> FlowRun:
    run = FlowRun(
        flow_name="test.flow",
        workflow_type="test_flow",
        state={},
        current_node="start",
        status=status,
        waiting_for="approval.received" if status == "waiting" else None,
        wait_deadline=wait_deadline,
        updated_at=updated_at,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_expire_timed_out_waits_marks_expired_wait_failed(db_session):
    run = _seed_flow_run(
        db_session,
        status="waiting",
        wait_deadline=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    count = asyncio.run(expire_timed_out_waits(db_session))

    db_session.refresh(run)
    assert count == 1
    assert run.status == "failed"
    assert run.wait_deadline is None
    assert run.error_detail["reason"] == "wait_timeout"
    assert run.error_detail["deadline"] is not None


def test_expire_timed_out_waits_leaves_future_deadline(db_session):
    run = _seed_flow_run(
        db_session,
        status="waiting",
        wait_deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    count = asyncio.run(expire_timed_out_waits(db_session))

    db_session.refresh(run)
    assert count == 0
    assert run.status == "waiting"
    assert run.error_detail is None


def test_expire_timed_out_waits_leaves_null_deadline(db_session):
    run = _seed_flow_run(
        db_session,
        status="waiting",
        wait_deadline=None,
    )

    count = asyncio.run(expire_timed_out_waits(db_session))

    db_session.refresh(run)
    assert count == 0
    assert run.status == "waiting"
    assert run.error_detail is None


def test_recover_stuck_runs_marks_old_running_run_failed(db_session):
    run = _seed_flow_run(
        db_session,
        status="running",
        updated_at=datetime.now(timezone.utc)
        - timedelta(minutes=settings.STUCK_RUN_THRESHOLD_MINUTES + 5),
    )

    count = asyncio.run(recover_stuck_runs(db_session))

    db_session.refresh(run)
    assert count == 1
    assert run.status == "failed"
    assert run.error_detail["reason"] == "stuck_run_recovered"
    assert run.error_detail["detected_at"] is not None


def test_recover_stuck_runs_leaves_recent_running_run(db_session):
    run = _seed_flow_run(
        db_session,
        status="running",
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    count = asyncio.run(recover_stuck_runs(db_session))

    db_session.refresh(run)
    assert count == 0
    assert run.status == "running"
    assert run.error_detail is None

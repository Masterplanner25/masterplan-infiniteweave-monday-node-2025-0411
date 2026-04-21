from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.waiting_flow_run import WaitingFlowRun
from AINDY.kernel.scheduler_engine import SchedulerEngine


def test_scheduler_orphaned_wait_recovery(db_session, test_user):
    run_id = "orphaned-flow-run"
    event_type = "task.completed"
    correlation_id = "trace-orphaned-flow-run"
    now = datetime.now(timezone.utc)

    db_session.add(
        FlowRun(
            id=run_id,
            flow_name="test.flow",
            workflow_type="test_flow",
            state={},
            current_node="wait_node",
            status="waiting",
            waiting_for=event_type,
            wait_deadline=now + timedelta(minutes=5),
            trace_id=correlation_id,
            user_id=test_user.id,
        )
    )
    db_session.add(
        WaitingFlowRun(
            run_id=run_id,
            event_type=event_type,
            correlation_id=correlation_id,
            waited_since=now - timedelta(minutes=1),
            max_wait_seconds=None,
            timeout_at=now + timedelta(minutes=5),
            eu_id="eu-orphaned-flow-run",
            priority="normal",
            instance_id="dead-instance",
        )
    )
    db_session.commit()

    scheduler = SchedulerEngine()

    assert run_id not in scheduler._waiting

    with patch(
        "AINDY.core.flow_run_rehydration.get_scheduler_engine",
        return_value=scheduler,
    ):
        recovered = scheduler.recover_orphaned_waits(db_session)

    assert recovered == 1
    assert run_id in scheduler._waiting
    assert callable(scheduler._waiting[run_id]["callback"])

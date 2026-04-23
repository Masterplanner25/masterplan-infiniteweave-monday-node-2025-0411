from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.waiting_flow_run import WaitingFlowRun
from AINDY.kernel.scheduler_engine import SchedulerEngine


def _register_wait(engine: SchedulerEngine, run_id: str) -> None:
    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        engine.register_wait(
            run_id=run_id,
            wait_for_event="order.completed",
            tenant_id="tenant-1",
            eu_id=f"eu-{run_id}",
            resume_callback=lambda: None,
        )


def _seed_wait_row(db_session, run_id: str) -> None:
    now = datetime.now(timezone.utc)
    row = db_session.query(WaitingFlowRun).filter(WaitingFlowRun.run_id == run_id).first()
    if row is None:
        row = WaitingFlowRun(
            run_id=run_id,
            event_type="order.completed",
            correlation_id=None,
            waited_since=now - timedelta(minutes=1),
            max_wait_seconds=None,
            timeout_at=now + timedelta(minutes=5),
            eu_id=f"eu-{run_id}",
            priority="normal",
            instance_id="test",
        )
        db_session.add(row)
    else:
        row.event_type = "order.completed"
        row.correlation_id = None
        row.waited_since = now - timedelta(minutes=1)
        row.max_wait_seconds = None
        row.timeout_at = now + timedelta(minutes=5)
        row.eu_id = f"eu-{run_id}"
        row.priority = "normal"
        row.instance_id = "test"
    db_session.commit()


def test_cleanup_removes_stale_waiting_entry(db_session, db_session_factory):
    engine = SchedulerEngine()
    _register_wait(engine, "run-dead")
    db_session.add(
        FlowRun(
            id="run-dead",
            flow_name="test.flow",
            workflow_type="test",
            state={},
            current_node="wait",
            status="failed",
            waiting_for="order.completed",
        )
    )
    _seed_wait_row(db_session, "run-dead")

    with patch("AINDY.db.database.SessionLocal", db_session_factory):
        removed = engine.cleanup_stale_waits()

    assert removed == 1
    assert "run-dead" not in engine._waiting


def test_cleanup_keeps_live_waiting_entry(db_session, db_session_factory):
    engine = SchedulerEngine()
    _register_wait(engine, "run-live")
    db_session.add(
        FlowRun(
            id="run-live",
            flow_name="test.flow",
            workflow_type="test",
            state={},
            current_node="wait",
            status="waiting",
            waiting_for="order.completed",
        )
    )
    _seed_wait_row(db_session, "run-live")

    with patch("AINDY.db.database.SessionLocal", db_session_factory):
        removed = engine.cleanup_stale_waits()

    assert removed == 0
    assert "run-live" in engine._waiting


def test_cleanup_noop_when_waiting_empty():
    engine = SchedulerEngine()

    with patch("AINDY.db.database.SessionLocal", side_effect=RuntimeError("should not be called")):
        removed = engine.cleanup_stale_waits()

    assert removed == 0


def test_cleanup_noop_on_db_failure():
    engine = SchedulerEngine()
    _register_wait(engine, "run-fail")

    with patch("AINDY.db.database.SessionLocal", side_effect=RuntimeError("db down")):
        removed = engine.cleanup_stale_waits()

    assert removed == 0
    assert "run-fail" in engine._waiting


def test_cleanup_deletes_waiting_flow_run_row(db_session, db_session_factory):
    engine = SchedulerEngine()
    _register_wait(engine, "run-stale")
    db_session.add(
        FlowRun(
            id="run-stale",
            flow_name="test.flow",
            workflow_type="test",
            state={},
            current_node="wait",
            status="failed",
            waiting_for="order.completed",
        )
    )
    _seed_wait_row(db_session, "run-stale")

    with patch("AINDY.db.database.SessionLocal", db_session_factory):
        removed = engine.cleanup_stale_waits()

    assert removed == 1
    remaining = (
        db_session.query(WaitingFlowRun)
        .filter(WaitingFlowRun.run_id == "run-stale")
        .first()
    )
    assert remaining is None

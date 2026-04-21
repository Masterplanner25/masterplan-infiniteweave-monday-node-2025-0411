from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from AINDY.db.models.waiting_flow_run import WaitingFlowRun
from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
from AINDY.kernel.resume_spec import RESUME_HANDLER_EU, ResumeSpec
from AINDY.kernel.scheduler_engine import PRIORITY_NORMAL, SchedulerEngine

try:
    import fakeredis

    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False


pytestmark = pytest.mark.skipif(not HAS_FAKEREDIS, reason="fakeredis not installed")


def _spec(run_id: str, *, eu_id: str | None = None) -> ResumeSpec:
    return ResumeSpec(
        handler=RESUME_HANDLER_EU,
        eu_id=eu_id or f"eu-{run_id}",
        tenant_id=f"tenant-{run_id}",
        run_id=run_id,
        eu_type="flow",
    )


def _seed_waiting_row(
    db_session,
    *,
    run_id: str,
    timeout_at: datetime,
    eu_id: str | None = None,
    priority: str = PRIORITY_NORMAL,
):
    row = WaitingFlowRun(
        run_id=run_id,
        event_type="time.wait",
        correlation_id=None,
        waited_since=datetime.now(timezone.utc) - timedelta(minutes=10),
        max_wait_seconds=None,
        timeout_at=timeout_at,
        eu_id=eu_id or f"eu-{run_id}",
        priority=priority,
        instance_id="instance-a",
    )
    db_session.add(row)
    db_session.commit()
    return row


def _shared_redis():
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


def test_cross_instance_time_wait_fires_when_due(db_session):
    shared_redis = _shared_redis()
    engine = SchedulerEngine()
    RedisWaitRegistry(shared_redis).register("run-t1", _spec("run-t1", eu_id="eu-t1"))
    _seed_waiting_row(
        db_session,
        run_id="run-t1",
        timeout_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        eu_id="eu-t1",
    )

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=shared_redis), patch(
        "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
        side_effect=lambda run_id: (
            db_session.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == run_id)
            .first()
        ),
    ):
        fired = engine.tick_time_waits()

    assert fired == 1
    item = engine.dequeue_next()
    assert item is not None
    assert item.run_id == "run-t1"
    assert item.execution_unit_id == "eu-t1"


def test_cross_instance_time_wait_not_fired_when_not_due(db_session):
    shared_redis = _shared_redis()
    engine = SchedulerEngine()
    RedisWaitRegistry(shared_redis).register("run-t2", _spec("run-t2"))
    _seed_waiting_row(
        db_session,
        run_id="run-t2",
        timeout_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=shared_redis), patch(
        "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
        side_effect=lambda run_id: (
            db_session.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == run_id)
            .first()
        ),
    ):
        fired = engine.tick_time_waits()

    assert fired == 0
    assert engine.dequeue_next() is None


def test_cross_instance_claim_is_exclusive_for_time_waits(db_session):
    shared_redis = _shared_redis()
    RedisWaitRegistry(shared_redis).register("run-race-time", _spec("run-race-time"))
    _seed_waiting_row(
        db_session,
        run_id="run-race-time",
        timeout_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    engine_a = SchedulerEngine()
    engine_b = SchedulerEngine()

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=shared_redis), patch(
        "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
        side_effect=lambda run_id: (
            db_session.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == run_id)
            .first()
        ),
    ):
        first = engine_a.tick_time_waits()
        second = engine_b.tick_time_waits()

    assert first + second == 1
    total_items = sum(engine.queue_depth()[PRIORITY_NORMAL] for engine in (engine_a, engine_b))
    assert total_items == 1


def test_cross_instance_time_tick_noop_when_redis_none():
    engine = SchedulerEngine()

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        fired = engine.tick_time_waits()

    assert fired == 0
    assert engine.dequeue_next() is None

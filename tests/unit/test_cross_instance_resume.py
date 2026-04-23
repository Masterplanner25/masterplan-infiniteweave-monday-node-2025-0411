from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from unittest.mock import patch

from AINDY.db.models.waiting_flow_run import WaitingFlowRun
from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
from AINDY.kernel.resume_spec import RESUME_HANDLER_EU, ResumeSpec
from AINDY.kernel.scheduler_engine import PRIORITY_NORMAL, SchedulerEngine, _cross_instance_resume


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str):
        self._values[key] = value
        self._ttls[key] = ttl
        return True

    def get(self, key: str):
        return self._values.get(key)

    def delete(self, key: str):
        existed = key in self._values
        self._values.pop(key, None)
        self._ttls.pop(key, None)
        return 1 if existed else 0

    def scan(self, cursor=0, match=None, count=100):
        keys = sorted(self._values.keys())
        if match is not None:
            prefix = str(match).removesuffix("*")
            keys = [key for key in keys if key.startswith(prefix)]
        return 0, keys


def _spec(run_id: str, *, eu_id: str | None = None) -> ResumeSpec:
    return ResumeSpec(
        handler=RESUME_HANDLER_EU,
        eu_id=eu_id or f"eu-{run_id}",
        tenant_id=f"tenant-{run_id}",
        run_id=run_id,
        eu_type="flow",
    )


def _ready_engine() -> SchedulerEngine:
    engine = SchedulerEngine()
    engine.mark_rehydration_complete()
    return engine


def _seed_waiting_row(
    db_session,
    *,
    run_id: str,
    event_type: str,
    correlation_id: str | None = None,
    eu_id: str | None = None,
    priority: str = PRIORITY_NORMAL,
):
    now = datetime.now(timezone.utc)
    row = WaitingFlowRun(
        run_id=run_id,
        event_type=event_type,
        correlation_id=correlation_id,
        waited_since=now - timedelta(minutes=1),
        max_wait_seconds=None,
        timeout_at=now + timedelta(minutes=5),
        eu_id=eu_id or f"eu-{run_id}",
        priority=priority,
        instance_id="instance-a",
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_local_resume_still_works():
    se = _ready_engine()
    resumed: list[str] = []

    se.register_wait(
        run_id="run-local",
        wait_for_event="task.completed",
        tenant_id="tenant-local",
        eu_id="eu-local",
        resume_callback=lambda: resumed.append("run-local"),
    )

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        count = se.notify_event("task.completed", broadcast=False)

    assert count == 1
    item = se.dequeue_next()
    assert item is not None
    item.run_callback()
    assert resumed == ["run-local"]


def test_cross_instance_resume_triggers_callback(db_session):
    engine = _ready_engine()
    fake_redis = _FakeRedis()
    spec = _spec("run-cross", eu_id="eu-cross")
    RedisWaitRegistry(fake_redis).register("run-cross", spec)
    _seed_waiting_row(
        db_session,
        run_id="run-cross",
        event_type="task.completed",
        correlation_id="trace-cross",
        eu_id="eu-cross",
    )

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=fake_redis), patch(
        "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
        side_effect=lambda run_id: (
            db_session.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == run_id)
            .first()
        ),
    ):
        count = engine.notify_event(
            "task.completed",
            correlation_id="trace-cross",
            broadcast=False,
        )

    assert count == 1
    item = engine.dequeue_next()
    assert item is not None
    assert item.run_id == "run-cross"
    assert item.execution_unit_id == "eu-cross"
    assert callable(item.run_callback)


def test_cross_instance_claim_is_exclusive(db_session):
    fake_redis = _FakeRedis()
    spec = _spec("run-race", eu_id="eu-race")
    RedisWaitRegistry(fake_redis).register("run-race", spec)
    _seed_waiting_row(
        db_session,
        run_id="run-race",
        event_type="task.completed",
        correlation_id="trace-race",
        eu_id="eu-race",
    )
    engine_a = _ready_engine()
    engine_b = _ready_engine()

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=fake_redis), patch(
        "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
        side_effect=lambda run_id: (
            db_session.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == run_id)
            .first()
        ),
    ):
        first = _cross_instance_resume(
            engine_a,
            "task.completed",
            "trace-race",
            skip_run_ids=set(),
        )
        second = _cross_instance_resume(
            engine_b,
            "task.completed",
            "trace-race",
            skip_run_ids=set(),
        )

    assert first == 1
    assert second == 0
    assert engine_a.dequeue_next() is not None
    assert engine_b.dequeue_next() is None


def test_cross_instance_skips_locally_owned_runs(testing_session_factory):
    engine = _ready_engine()
    fake_redis = _FakeRedis()
    spec = _spec("run-owned", eu_id="eu-owned")
    RedisWaitRegistry(fake_redis).register("run-owned", spec)
    db = testing_session_factory()
    _seed_waiting_row(
        db,
        run_id="run-owned",
        event_type="task.completed",
        correlation_id="trace-owned",
        eu_id="eu-owned",
    )
    local_calls: list[str] = []
    try:
        engine.register_wait(
            run_id="run-owned",
            wait_for_event="task.completed",
            tenant_id="tenant-owned",
            eu_id="eu-owned",
            resume_callback=lambda: local_calls.append("run-owned"),
            correlation_id="trace-owned",
        )

        with patch("AINDY.kernel.event_bus.get_redis_client", return_value=fake_redis), patch(
            "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
            side_effect=lambda run_id: (
                db.query(WaitingFlowRun)
                .filter(WaitingFlowRun.run_id == run_id)
                .first()
            ),
        ):
            count = engine.notify_event(
                "task.completed",
                correlation_id="trace-owned",
                broadcast=False,
            )

        assert count == 1
        item = engine.dequeue_next()
        assert item is not None
        assert item.run_id == "run-owned"
        assert engine.dequeue_next() is None
    finally:
        db.close()


def test_cross_instance_noop_when_redis_none():
    engine = _ready_engine()

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        resumed = _cross_instance_resume(
            engine,
            "task.completed",
            None,
            skip_run_ids=set(),
        )

    assert resumed == 0
    assert engine.dequeue_next() is None


def test_cross_instance_skips_stale_redis_key_with_no_db_record():
    engine = _ready_engine()
    fake_redis = _FakeRedis()
    RedisWaitRegistry(fake_redis).register("run-stale", _spec("run-stale"))

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=fake_redis):
        resumed = _cross_instance_resume(
            engine,
            "task.completed",
            None,
            skip_run_ids=set(),
        )

    assert resumed == 0
    assert engine.dequeue_next() is None


def test_cross_instance_skips_wrong_event_type(db_session):
    engine = _ready_engine()
    fake_redis = _FakeRedis()
    RedisWaitRegistry(fake_redis).register("run-wrong-event", _spec("run-wrong-event"))
    _seed_waiting_row(
        db_session,
        run_id="run-wrong-event",
        event_type="order.completed",
        correlation_id=str(uuid.uuid4()),
    )

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=fake_redis), patch(
        "AINDY.kernel.scheduler_engine._load_wait_entry_from_db",
        side_effect=lambda run_id: (
            db_session.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == run_id)
            .first()
        ),
    ):
        resumed = _cross_instance_resume(
            engine,
            "payment.failed",
            None,
            skip_run_ids=set(),
        )

    assert resumed == 0
    assert engine.dequeue_next() is None

from __future__ import annotations

from unittest.mock import patch

from AINDY.kernel.scheduler_engine import SchedulerEngine


def test_event_buffered_before_rehydration():
    engine = SchedulerEngine()

    count = engine.notify_event("order.completed", broadcast=False)

    assert count == 0
    assert engine._pre_rehydration_buffer == [("order.completed", None)]
    assert engine._waiting == {}


def test_buffered_event_replayed_on_mark_rehydration_complete():
    engine = SchedulerEngine()
    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        engine.register_wait(
            run_id="run-1",
            wait_for_event="order.completed",
            tenant_id="tenant-1",
            eu_id="eu-1",
            resume_callback=lambda: None,
        )

    buffered = engine.notify_event("order.completed", broadcast=False)
    assert buffered == 0
    assert engine.queue_depth() == {"high": 0, "normal": 0, "low": 0}

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        engine.mark_rehydration_complete()

    item = engine.dequeue_next()
    assert item is not None
    assert item.run_id == "run-1"


def test_no_double_replay_on_second_notify_event():
    engine = SchedulerEngine()
    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        engine.register_wait(
            run_id="run-1",
            wait_for_event="order.completed",
            tenant_id="tenant-1",
            eu_id="eu-1",
            resume_callback=lambda: None,
        )

    engine.notify_event("order.completed", broadcast=False)
    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        engine.mark_rehydration_complete()

    first = engine.dequeue_next()
    assert first is not None

    with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
        second_count = engine.notify_event("order.completed", broadcast=False)

    assert second_count == 0
    assert engine.dequeue_next() is None


def test_buffer_overflow_drops_events_and_logs_error():
    engine = SchedulerEngine()

    with patch("AINDY.kernel.scheduler_engine._MAX_PRE_REHYDRATION_BUFFER", 3):
        for idx in range(5):
            count = engine.notify_event(f"evt.{idx}", broadcast=False)
            assert count == 0

    assert engine._pre_rehydration_buffer == [
        ("evt.0", None),
        ("evt.1", None),
        ("evt.2", None),
    ]


def test_reset_clears_buffer_and_rehydration_flag():
    engine = SchedulerEngine()
    engine.notify_event("order.completed", broadcast=False)
    assert engine._pre_rehydration_buffer

    engine.mark_rehydration_complete()
    assert engine.is_rehydrated() is True

    engine.reset()

    assert engine._pre_rehydration_buffer == []
    assert engine.is_rehydrated() is False

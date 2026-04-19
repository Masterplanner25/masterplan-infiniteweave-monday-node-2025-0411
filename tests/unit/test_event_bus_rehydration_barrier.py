"""Unit tests for EventBus pre-rehydration buffering and drain."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from AINDY.kernel.event_bus import EventBus, _MAX_BUFFER_SIZE
from AINDY.kernel.scheduler_engine import SchedulerEngine

_PATCH_TARGET = "AINDY.kernel.scheduler_engine.get_scheduler_engine"


def _raw_payload(event_type: str, correlation_id: str | None = None) -> str:
    import json
    return json.dumps({
        "event_type": event_type,
        "correlation_id": correlation_id,
        "source_instance_id": "other-instance",
    })


def test_pre_rehydration_events_are_buffered_not_dispatched():
    """Events arriving before mark_rehydration_complete() go to the buffer."""
    engine = SchedulerEngine()  # not yet rehydrated
    notify_spy = MagicMock()
    engine.notify_event = notify_spy
    bus = EventBus()

    with patch(_PATCH_TARGET, return_value=engine):
        bus._handle_message(_raw_payload("op.done", "corr-1"))
        bus._handle_message(_raw_payload("op.done", "corr-2"))

    notify_spy.assert_not_called()
    assert bus._pre_rehydration_buffer == [
        ("op.done", "corr-1"),
        ("op.done", "corr-2"),
    ]


def test_drain_dispatches_all_buffered_events():
    """drain_buffered_events() calls notify_event for every buffered entry."""
    engine = SchedulerEngine()
    engine.mark_rehydration_complete()
    notify_spy = MagicMock()
    engine.notify_event = notify_spy
    bus = EventBus()
    bus._pre_rehydration_buffer = [
        ("op.done", "c1"),
        ("flow.resumed", "c2"),
    ]

    with patch(_PATCH_TARGET, return_value=engine):
        drained = bus.drain_buffered_events()

    assert drained == 2
    assert bus._pre_rehydration_buffer == []
    notify_spy.assert_any_call("op.done", correlation_id="c1", broadcast=False)
    notify_spy.assert_any_call("flow.resumed", correlation_id="c2", broadcast=False)


def test_drain_is_idempotent():
    """Calling drain_buffered_events() twice is safe; second call returns 0."""
    engine = SchedulerEngine()
    engine.mark_rehydration_complete()
    bus = EventBus()
    bus._pre_rehydration_buffer = [("evt", None)]

    with patch(_PATCH_TARGET, return_value=engine):
        first = bus.drain_buffered_events()
        second = bus.drain_buffered_events()

    assert first == 1
    assert second == 0


def test_buffer_bounded_at_max_size():
    """Buffer never grows beyond _MAX_BUFFER_SIZE; excess events are dropped."""
    engine = SchedulerEngine()  # not yet rehydrated
    bus = EventBus()

    with patch(_PATCH_TARGET, return_value=engine):
        for i in range(_MAX_BUFFER_SIZE + 50):
            bus._handle_message(_raw_payload(f"evt.{i}"))

    assert len(bus._pre_rehydration_buffer) == _MAX_BUFFER_SIZE


def test_post_rehydration_events_dispatched_directly():
    """After mark_rehydration_complete(), events bypass the buffer entirely."""
    engine = SchedulerEngine()
    engine.mark_rehydration_complete()
    notify_spy = MagicMock()
    engine.notify_event = notify_spy
    bus = EventBus()

    with patch(_PATCH_TARGET, return_value=engine):
        bus._handle_message(_raw_payload("op.done", "c99"))

    assert bus._pre_rehydration_buffer == []
    notify_spy.assert_called_once_with(
        "op.done", correlation_id="c99", broadcast=False
    )

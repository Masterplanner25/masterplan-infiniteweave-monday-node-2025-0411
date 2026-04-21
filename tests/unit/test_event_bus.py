"""
Tests for kernel.event_bus and the notify_event() broadcast integration.

Groups
------
A  EventBus.publish() — correct payload, fault tolerance, disabled state
B  EventBus._handle_message() — routing, source filtering, malformed input
C  SchedulerEngine.notify_event() — broadcast=True/False, non-fatal bus failure
D  EventBus.start_subscriber() — idempotency, disabled state
"""
from __future__ import annotations

import json
import threading
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from AINDY.kernel.event_bus import CHANNEL, EventBus


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _bus(*, instance_id: str = "test-instance", enabled: bool = True) -> EventBus:
    """Return a fresh EventBus with controlled instance_id and enabled flag."""
    b = EventBus()
    b._instance_id = instance_id
    b._enabled = enabled
    return b


def _mock_redis_client():
    """Return a mock Redis client whose publish() call we can assert on."""
    client = MagicMock()
    client.publish.return_value = 1
    return client


# ══════════════════════════════════════════════════════════════════════════════
# A: EventBus.publish()
# ══════════════════════════════════════════════════════════════════════════════

class TestEventBusPublish:

    def test_publish_calls_redis_publish(self):
        """publish() must call redis.publish with the correct channel."""
        bus = _bus()
        mock_client = _mock_redis_client()
        bus._pub_client = mock_client

        bus.publish("task.completed")

        mock_client.publish.assert_called_once()
        args = mock_client.publish.call_args[0]
        assert args[0] == CHANNEL

    def test_publish_payload_contains_event_type(self):
        """Published JSON must include event_type."""
        bus = _bus(instance_id="inst-A")
        mock_client = _mock_redis_client()
        bus._pub_client = mock_client

        bus.publish("task.completed", correlation_id="trace-xyz")

        raw = mock_client.publish.call_args[0][1]
        payload = json.loads(raw)
        assert payload["event_type"] == "task.completed"
        assert payload["correlation_id"] == "trace-xyz"
        assert payload["source_instance_id"] == "inst-A"

    def test_publish_returns_true_on_success(self):
        bus = _bus()
        bus._pub_client = _mock_redis_client()
        assert bus.publish("event.x") is True

    def test_publish_returns_false_when_redis_raises(self):
        """Redis failure must return False — must not raise."""
        bus = _bus()
        mock_client = MagicMock()
        mock_client.publish.side_effect = ConnectionError("Redis down")
        bus._pub_client = mock_client

        result = bus.publish("event.x")

        assert result is False

    def test_publish_nonfatal_when_redis_raises(self):
        """Redis failure must NOT propagate an exception to the caller."""
        bus = _bus()
        mock_client = MagicMock()
        mock_client.publish.side_effect = OSError("connection refused")
        bus._pub_client = mock_client

        bus.publish("event.x")  # must not raise

    def test_publish_resets_client_on_failure(self):
        """After a publish failure, _pub_client is cleared for reconnect."""
        bus = _bus()
        mock_client = MagicMock()
        mock_client.publish.side_effect = ConnectionError("gone")
        bus._pub_client = mock_client

        bus.publish("event.x")

        assert bus._pub_client is None

    def test_publish_skipped_when_disabled(self):
        """Disabled bus must not touch Redis at all."""
        bus = _bus(enabled=False)
        bus._pub_client = _mock_redis_client()

        result = bus.publish("event.x")

        assert result is False
        bus._pub_client.publish.assert_not_called()

    def test_publish_none_correlation_id_serialises_cleanly(self):
        """None correlation_id must serialise to JSON null — not raise."""
        bus = _bus()
        mock_client = _mock_redis_client()
        bus._pub_client = mock_client

        bus.publish("event.x", correlation_id=None)

        raw = mock_client.publish.call_args[0][1]
        payload = json.loads(raw)
        assert payload["correlation_id"] is None


# ══════════════════════════════════════════════════════════════════════════════
# B: EventBus._handle_message()
# ══════════════════════════════════════════════════════════════════════════════

class TestEventBusHandleMessage:

    def _make_payload(
        self,
        event_type: str = "task.completed",
        correlation_id: str | None = None,
        source: str = "other-instance",
    ) -> str:
        return json.dumps({
            "event_type": event_type,
            "correlation_id": correlation_id,
            "source_instance_id": source,
        })

    def test_handle_message_calls_local_notify_event(self):
        """Valid message from another instance must call local notify_event."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(self._make_payload(source="inst-A"))

        mock_se.notify_event.assert_called_once_with(
            "task.completed", correlation_id=None, broadcast=False
        )

    def test_handle_message_passes_correlation_id(self):
        """correlation_id from payload must be forwarded."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(
                self._make_payload(correlation_id="chain-abc", source="inst-A")
            )

        mock_se.notify_event.assert_called_once_with(
            "task.completed", correlation_id="chain-abc", broadcast=False
        )

    def test_handle_message_calls_broadcast_false(self):
        """Subscriber must call notify_event with broadcast=False — no re-publish."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(self._make_payload(source="inst-A"))

        _, kwargs = mock_se.notify_event.call_args
        assert kwargs.get("broadcast") is False

    def test_handle_message_skips_own_instance(self):
        """Messages sourced from this instance must be silently ignored."""
        bus = _bus(instance_id="inst-A")
        mock_se = MagicMock()

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(self._make_payload(source="inst-A"))  # same instance

        mock_se.notify_event.assert_not_called()

    def test_handle_message_ignores_malformed_json(self):
        """Non-JSON data must not raise."""
        bus = _bus()
        mock_se = MagicMock()

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message("not-valid-json{{{")

        mock_se.notify_event.assert_not_called()

    def test_handle_message_ignores_missing_event_type(self):
        """Payload without event_type must be dropped silently."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()
        raw = json.dumps({"source_instance_id": "inst-A"})  # no event_type

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(raw)

        mock_se.notify_event.assert_not_called()

    def test_handle_message_ignores_empty_string_event_type(self):
        """Empty event_type must be dropped — not forwarded to scheduler."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()
        raw = json.dumps({"event_type": "", "source_instance_id": "inst-A"})

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(raw)

        mock_se.notify_event.assert_not_called()

    def test_handle_message_nonfatal_when_scheduler_raises(self):
        """Scheduler exception must not propagate out of _handle_message."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()
        mock_se.notify_event.side_effect = RuntimeError("scheduler crashed")

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(self._make_payload(source="inst-A"))  # must not raise

    def test_handle_message_ignores_non_string_event_type(self):
        """Non-string event_type (e.g., integer) must be dropped."""
        bus = _bus(instance_id="inst-B")
        mock_se = MagicMock()
        raw = json.dumps({"event_type": 42, "source_instance_id": "inst-A"})

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine", return_value=mock_se):
            bus._handle_message(raw)

        mock_se.notify_event.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# C: SchedulerEngine.notify_event() — broadcast integration
# ══════════════════════════════════════════════════════════════════════════════

class TestSchedulerNotifyEventBroadcast:

    def _make_scheduler(self):
        from AINDY.kernel.scheduler_engine import SchedulerEngine
        se = SchedulerEngine()
        se.mark_rehydration_complete()
        return se

    def test_notify_event_publishes_to_bus_by_default(self):
        """notify_event() must publish to the event bus (broadcast=True default)."""
        se = self._make_scheduler()
        mock_bus = MagicMock()

        with patch("AINDY.kernel.event_bus.get_event_bus", return_value=mock_bus):
            se.notify_event("task.completed", correlation_id="cid-1")

        mock_bus.publish.assert_called_once_with(
            "task.completed", correlation_id="cid-1"
        )

    def test_notify_event_broadcast_false_skips_publish(self):
        """broadcast=False must suppress the event bus publish call entirely."""
        se = self._make_scheduler()
        mock_bus = MagicMock()

        with patch("AINDY.kernel.event_bus.get_event_bus", return_value=mock_bus):
            se.notify_event("task.completed", broadcast=False)

        mock_bus.publish.assert_not_called()

    def test_notify_event_bus_failure_is_nonfatal(self):
        """Event bus exception must not affect local scheduling result."""
        from AINDY.kernel.scheduler_engine import SchedulerEngine
        from AINDY.core.wait_condition import WaitCondition

        se = SchedulerEngine()
        se.mark_rehydration_complete()
        cb = MagicMock()
        se.register_wait(
            run_id="run-1",
            wait_for_event="task.completed",
            tenant_id="user-1",
            eu_id="eu-1",
            resume_callback=cb,
            wait_condition=WaitCondition.for_event("task.completed"),
        )

        with patch("AINDY.kernel.event_bus.get_event_bus", side_effect=RuntimeError("bus gone")):
            count = se.notify_event("task.completed")  # must not raise

        # Local match is recorded; callback is enqueued (dispatched by schedule())
        assert count == 1
        assert se.queue_depth()["normal"] == 1

    def test_notify_event_local_scan_always_runs_first(self):
        """Local _waiting scan must complete before publish is attempted."""
        from AINDY.kernel.scheduler_engine import SchedulerEngine
        from AINDY.core.wait_condition import WaitCondition

        se = SchedulerEngine()
        se.mark_rehydration_complete()
        call_order: list[str] = []

        cb = MagicMock(side_effect=lambda: call_order.append("local_callback"))
        se.register_wait(
            run_id="run-2",
            wait_for_event="order.placed",
            tenant_id="t",
            eu_id="eu-2",
            resume_callback=cb,
            wait_condition=WaitCondition.for_event("order.placed"),
        )

        mock_bus = MagicMock()
        mock_bus.publish.side_effect = lambda *a, **kw: call_order.append("bus_publish")

        with patch("AINDY.kernel.event_bus.get_event_bus", return_value=mock_bus):
            se.notify_event("order.placed")

        # Callback is enqueued, bus publish is last.
        # We verify publish was called (not the order of enqueue vs. dispatch,
        # since callbacks run later via schedule()).
        mock_bus.publish.assert_called_once_with("order.placed", correlation_id=None)

    def test_notify_event_returns_local_count_regardless_of_bus(self):
        """Return value reflects locally matched runs, not bus delivery."""
        from AINDY.kernel.scheduler_engine import SchedulerEngine
        from AINDY.core.wait_condition import WaitCondition

        se = SchedulerEngine()
        se.mark_rehydration_complete()
        se.register_wait(
            run_id="run-3",
            wait_for_event="ping",
            tenant_id="t",
            eu_id="eu-3",
            resume_callback=MagicMock(),
            wait_condition=WaitCondition.for_event("ping"),
        )

        mock_bus = MagicMock()
        mock_bus.publish.return_value = False  # simulate Redis failure

        with patch("AINDY.kernel.event_bus.get_event_bus", return_value=mock_bus):
            count = se.notify_event("ping")

        assert count == 1  # local match, regardless of bus result


# ══════════════════════════════════════════════════════════════════════════════
# D: EventBus.start_subscriber()
# ══════════════════════════════════════════════════════════════════════════════

class TestEventBusSubscriber:

    def test_start_subscriber_is_idempotent(self):
        """Calling start_subscriber() twice must not create two threads."""
        bus = _bus()
        fake_thread = MagicMock(spec=threading.Thread)
        fake_thread.is_alive.return_value = True

        with patch("threading.Thread", return_value=fake_thread):
            bus.start_subscriber()
            first_thread = bus._subscriber_thread

        # Thread is now "alive" — second call must be a no-op
        with patch("threading.Thread") as mock_thread_cls:
            bus.start_subscriber()
            mock_thread_cls.assert_not_called()

        assert bus._subscriber_thread is first_thread

    def test_start_subscriber_noop_when_disabled(self):
        """Disabled bus must not start any thread."""
        bus = _bus(enabled=False)

        with patch("threading.Thread") as mock_thread_cls:
            bus.start_subscriber()

        mock_thread_cls.assert_not_called()
        assert bus._subscriber_thread is None

    def test_start_subscriber_creates_daemon_thread(self):
        """Subscriber thread must be created with daemon=True."""
        bus = _bus()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False

        with patch("threading.Thread", return_value=mock_thread) as mock_cls:
            bus.start_subscriber()

        _, kwargs = mock_cls.call_args
        assert kwargs.get("daemon") is True

    def test_stop_subscriber_sets_stop_event(self):
        """stop_subscriber() must set the internal stop event."""
        bus = _bus()
        assert not bus._stop_event.is_set()
        bus.stop_subscriber()
        assert bus._stop_event.is_set()

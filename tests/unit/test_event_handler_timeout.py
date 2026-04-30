from __future__ import annotations

import time

import prometheus_client as _prom
import pytest

pytestmark = pytest.mark.skipif(
    getattr(_prom, "_is_stub", False),
    reason="requires real prometheus_client: pip install -r AINDY/requirements.txt",
)

from AINDY.config import settings
from AINDY.platform_layer import event_service
from AINDY.platform_layer.metrics import REGISTRY


def _metric_value(name: str, **labels) -> float:
    value = REGISTRY.get_sample_value(name, labels=labels)
    return float(value or 0.0)


def _dispatch() -> int:
    return event_service.dispatch_internal_event_handlers(
        db=None,
        event_type="event.test",
        event_id="event-1",
        payload={"ok": True},
        user_id=None,
        trace_id=None,
        source="test",
    )


def test_fast_handler_completes(monkeypatch, caplog):
    calls: list[str] = []

    def fast_handler(event):
        calls.append(event["event_type"])

    monkeypatch.setattr(settings, "AINDY_EVENT_HANDLER_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(event_service, "_INTERNAL_HANDLERS", {"event.test": [fast_handler]})
    before = _metric_value("aindy_event_handler_timeouts_total", event_type="event.test")
    histogram_before = _metric_value(
        "aindy_event_handler_duration_seconds_count",
        event_type="event.test",
        handler_name="fast_handler",
        result="ok",
    )

    dispatched = _dispatch()

    assert dispatched == 1
    assert calls == ["event.test"]
    assert _metric_value("aindy_event_handler_timeouts_total", event_type="event.test") == before
    assert (
        _metric_value(
            "aindy_event_handler_duration_seconds_count",
            event_type="event.test",
            handler_name="fast_handler",
            result="ok",
        )
        == histogram_before + 1.0
    )


def test_slow_handler_times_out(monkeypatch, caplog):
    def slow_handler(event):
        time.sleep(0.2)

    monkeypatch.setattr(settings, "AINDY_EVENT_HANDLER_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(event_service, "_INTERNAL_HANDLERS", {"event.test": [slow_handler]})
    before = _metric_value("aindy_event_handler_timeouts_total", event_type="event.test")
    histogram_before = _metric_value(
        "aindy_event_handler_duration_seconds_count",
        event_type="event.test",
        handler_name="slow_handler",
        result="timeout",
    )

    with caplog.at_level("WARNING"):
        dispatched = _dispatch()

    assert dispatched == 0
    assert _metric_value("aindy_event_handler_timeouts_total", event_type="event.test") == before + 1.0
    assert any("timed out" in message for message in caplog.messages)
    assert (
        _metric_value(
            "aindy_event_handler_duration_seconds_count",
            event_type="event.test",
            handler_name="slow_handler",
            result="timeout",
        )
        == histogram_before + 1.0
    )


def test_handler_exception_is_logged_without_timeout_metric(monkeypatch, caplog):
    def exploding_handler(event):
        raise RuntimeError("boom")

    monkeypatch.setattr(settings, "AINDY_EVENT_HANDLER_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(event_service, "_INTERNAL_HANDLERS", {"event.test": [exploding_handler]})
    before = _metric_value("aindy_event_handler_timeouts_total", event_type="event.test")
    histogram_before = _metric_value(
        "aindy_event_handler_duration_seconds_count",
        event_type="event.test",
        handler_name="exploding_handler",
        result="error",
    )

    with caplog.at_level("WARNING"):
        dispatched = _dispatch()

    assert dispatched == 0
    assert _metric_value("aindy_event_handler_timeouts_total", event_type="event.test") == before
    assert any("boom" in message for message in caplog.messages)
    assert (
        _metric_value(
            "aindy_event_handler_duration_seconds_count",
            event_type="event.test",
            handler_name="exploding_handler",
            result="error",
        )
        == histogram_before + 1.0
    )


def test_timeout_does_not_block_subsequent_handlers(monkeypatch):
    calls: list[str] = []

    def handler_one(event):
        calls.append("one")

    def handler_two(event):
        time.sleep(0.2)

    def handler_three(event):
        calls.append("three")

    monkeypatch.setattr(settings, "AINDY_EVENT_HANDLER_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        event_service,
        "_INTERNAL_HANDLERS",
        {"event.test": [handler_one, handler_two, handler_three]},
    )

    dispatched = _dispatch()

    assert dispatched == 2
    assert calls == ["one", "three"]


def test_timeout_uses_configured_settings_value(monkeypatch, caplog):
    def slow_handler(event):
        time.sleep(0.5)

    monkeypatch.setattr(settings, "AINDY_EVENT_HANDLER_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(event_service, "_INTERNAL_HANDLERS", {"event.test": [slow_handler]})

    started_at = time.perf_counter()
    with caplog.at_level("WARNING"):
        dispatched = _dispatch()
    elapsed = time.perf_counter() - started_at

    assert dispatched == 0
    assert elapsed < 0.4
    assert any("timeout_seconds=0.10" in message for message in caplog.messages)

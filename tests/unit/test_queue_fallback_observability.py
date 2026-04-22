from __future__ import annotations

import logging

import pytest


def _configure_non_test_env(monkeypatch, distributed_queue, *, redis_url: str | None = "redis://example") -> None:
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("EXECUTION_MODE", "thread")
    if redis_url is None:
        monkeypatch.delenv("REDIS_URL", raising=False)
    else:
        monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setattr(distributed_queue.settings, "REDIS_URL", redis_url)
    monkeypatch.setattr(distributed_queue.settings, "ENV", "development")
    monkeypatch.setattr(distributed_queue.settings, "AINDY_REQUIRE_REDIS", False)


def _fake_redis_backend(distributed_queue, *, should_fail: bool):
    class FakeRedisBackend(distributed_queue.DistributedQueueBackend):
        def __init__(self, url: str, queue_name: str = distributed_queue.QUEUE_NAME_DEFAULT, **_kwargs) -> None:
            self.url = url
            self.queue_name = queue_name

        def enqueue(self, payload):
            raise NotImplementedError

        def dequeue(self, timeout: int = 5):
            raise NotImplementedError

        def ack(self, job_id: str) -> None:
            return None

        def fail(self, job_id: str, error: str = "") -> None:
            return None

        def get_dlq_depth(self) -> int:
            return 0

        def get_metrics(self) -> dict:
            return {
                "queue_depth": 0,
                "in_flight_count": 0,
                "failed_jobs": 0,
                "delayed_jobs": 0,
                "dlq_depth": 0,
                "max_queue_size": 100,
                "total_pending_jobs": 0,
                "saturation_threshold": 100,
            }

        @property
        def backend_name(self) -> str:
            return "redis"

        def assert_ready(self) -> None:
            if should_fail:
                raise ConnectionError("redis down")

    return FakeRedisBackend


@pytest.fixture(autouse=True)
def _reset_queue_backend():
    from AINDY.core.distributed_queue import reset_queue

    reset_queue()
    yield
    reset_queue()


def test_queue_uses_redis_when_available(monkeypatch):
    from AINDY.core import distributed_queue
    from AINDY.platform_layer.metrics import queue_backend_fallback_total, queue_backend_mode

    _configure_non_test_env(monkeypatch, distributed_queue)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(distributed_queue, "_emit_queue_backend_event", lambda event_type, payload: events.append((event_type, payload)))
    monkeypatch.setattr(distributed_queue, "RedisQueueBackend", _fake_redis_backend(distributed_queue, should_fail=False))
    baseline = queue_backend_fallback_total._value.get()

    backend = distributed_queue.get_queue()

    assert backend.backend_name == "redis"
    assert queue_backend_mode._value.get() == 1
    assert queue_backend_fallback_total._value.get() == baseline
    assert events == []


def test_queue_falls_back_to_memory_when_redis_unavailable(monkeypatch, caplog):
    from AINDY.core import distributed_queue
    from AINDY.platform_layer.metrics import queue_backend_fallback_total, queue_backend_mode

    _configure_non_test_env(monkeypatch, distributed_queue)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(distributed_queue, "_emit_queue_backend_event", lambda event_type, payload: events.append((event_type, payload)))
    monkeypatch.setattr(distributed_queue, "RedisQueueBackend", _fake_redis_backend(distributed_queue, should_fail=True))
    baseline = queue_backend_fallback_total._value.get()
    caplog.set_level(logging.WARNING)

    backend = distributed_queue.get_queue()

    assert isinstance(backend, distributed_queue.InMemoryQueueBackend)
    assert backend.degraded is True
    assert queue_backend_mode._value.get() == 0
    assert queue_backend_fallback_total._value.get() == baseline + 1
    assert any("jobs will NOT be shared across instances" in record.message for record in caplog.records)
    assert events and events[0][0] == "system.queue.backend_degraded"


def test_queue_requires_redis_when_configured(monkeypatch):
    from AINDY.core import distributed_queue

    _configure_non_test_env(monkeypatch, distributed_queue)
    monkeypatch.setattr(distributed_queue.settings, "AINDY_REQUIRE_REDIS", True)
    monkeypatch.setattr(distributed_queue, "RedisQueueBackend", _fake_redis_backend(distributed_queue, should_fail=True))

    with pytest.raises(RuntimeError, match="AINDY_REQUIRE_REDIS=true but Redis is unavailable"):
        distributed_queue.get_queue()


def test_reconnect_switches_back_to_redis(monkeypatch):
    from AINDY.core import distributed_queue
    from AINDY.platform_layer.metrics import queue_backend_mode

    _configure_non_test_env(monkeypatch, distributed_queue)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(distributed_queue, "_emit_queue_backend_event", lambda event_type, payload: events.append((event_type, payload)))
    monkeypatch.setattr(distributed_queue, "RedisQueueBackend", _fake_redis_backend(distributed_queue, should_fail=True))
    backend = distributed_queue.get_queue()
    assert isinstance(backend, distributed_queue.InMemoryQueueBackend)

    monkeypatch.setattr(distributed_queue, "RedisQueueBackend", _fake_redis_backend(distributed_queue, should_fail=False))

    assert distributed_queue.attempt_queue_backend_reconnect() is True
    assert distributed_queue.get_queue().backend_name == "redis"
    assert queue_backend_mode._value.get() == 1
    assert events[-1][0] == "system.queue.backend_recovered"


def test_reconnect_failure_keeps_memory_backend(monkeypatch, caplog):
    from AINDY.core import distributed_queue
    from AINDY.platform_layer.metrics import queue_backend_mode

    _configure_non_test_env(monkeypatch, distributed_queue)
    monkeypatch.setattr(distributed_queue, "_emit_queue_backend_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(distributed_queue, "RedisQueueBackend", _fake_redis_backend(distributed_queue, should_fail=True))
    backend = distributed_queue.get_queue()
    assert isinstance(backend, distributed_queue.InMemoryQueueBackend)

    caplog.set_level(logging.DEBUG)
    assert distributed_queue.attempt_queue_backend_reconnect() is False
    assert distributed_queue.get_queue().backend_name == "inmemory"
    assert queue_backend_mode._value.get() == 0
    assert not any(record.levelno >= logging.WARNING and "Redis reconnect attempt failed" in record.message for record in caplog.records)
    assert any(record.levelno == logging.DEBUG and "Redis reconnect attempt failed" in record.message for record in caplog.records)


def test_health_service_reports_queue_degraded(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.health_service import DependencyStatus

    monkeypatch.setattr(
        health_service,
        "check_postgres",
        lambda: DependencyStatus(name="postgres", status="ok", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda: DependencyStatus(name="redis", status="unavailable", critical=False),
    )
    monkeypatch.setattr(
        health_service,
        "check_queue",
        lambda: DependencyStatus(
            name="queue",
            status="degraded",
            critical=False,
            metadata={"backend": "memory", "degraded": True, "redis_available": False},
        ),
    )
    monkeypatch.setattr(
        health_service,
        "check_mongo",
        lambda: DependencyStatus(name="mongo", status="ok", critical=False),
    )
    monkeypatch.setattr(
        health_service,
        "check_schema",
        lambda: DependencyStatus(name="schema", status="ok", critical=True),
    )

    payload = health_service.get_system_health(force=True).to_dict()

    assert payload["dependencies"]["queue"]["backend"] == "memory"
    assert payload["dependencies"]["queue"]["degraded"] is True
    assert payload["dependencies"]["queue"]["redis_available"] is False

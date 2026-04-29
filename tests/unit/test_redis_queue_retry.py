from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

redis = pytest.importorskip(
    "redis",
    reason="redis package not installed — run: pip install redis==5.0.4",
)

# redis and (optionally) fakeredis must be installed for these tests:
#   pip install redis==5.0.4 fakeredis
# These packages are in AINDY/requirements.txt. If they are missing
# from your environment, run: pip install -r AINDY/requirements.txt

from AINDY.core.distributed_queue import QueueJobPayload, RedisQueueBackend


def _make_backend(**kwargs) -> RedisQueueBackend:
    client = MagicMock()
    registered_scripts: list[MagicMock] = []

    def _register_script(_source):
        script = MagicMock(return_value=0)
        registered_scripts.append(script)
        return script

    client.register_script.side_effect = _register_script

    with patch("redis.from_url", return_value=client):
        backend = RedisQueueBackend("redis://example", **kwargs)

    backend._redis = client
    backend._registered_scripts = registered_scripts  # type: ignore[attr-defined]
    return backend


def test_retries_on_connection_error():
    backend = _make_backend()
    job = QueueJobPayload(job_id="job-1", task_name="ping")

    backend._enqueue_with_capacity.side_effect = [
        redis.ConnectionError("down-1"),
        redis.ConnectionError("down-2"),
        1,
    ]

    backend.enqueue(job)

    assert backend._enqueue_with_capacity.call_count == 3
    assert backend._failure_count == 0
    assert backend._open_until == 0.0


def test_circuit_breaker_opens_after_threshold():
    backend = _make_backend(
        circuit_breaker_threshold=2,
        circuit_breaker_open_seconds=30.0,
    )
    job = QueueJobPayload(job_id="job-1", task_name="ping")

    backend._enqueue_with_capacity.side_effect = redis.ConnectionError("down")

    with pytest.raises(redis.ConnectionError):
        backend.enqueue(job)

    assert backend._enqueue_with_capacity.call_count == 3
    assert backend._failure_count == 1

    with pytest.raises(redis.ConnectionError):
        backend.enqueue(job)

    assert backend._enqueue_with_capacity.call_count == 6
    assert backend._failure_count == 2
    assert backend._open_until > 0.0

    with pytest.raises(redis.ConnectionError, match="Circuit breaker open"):
        backend.enqueue(job)

    assert backend._enqueue_with_capacity.call_count == 6


def test_circuit_breaker_resets_on_success():
    backend = _make_backend(
        circuit_breaker_threshold=1,
        circuit_breaker_open_seconds=30.0,
    )
    job = QueueJobPayload(job_id="job-1", task_name="ping")

    backend._enqueue_with_capacity.side_effect = redis.ConnectionError("down")

    with pytest.raises(redis.ConnectionError):
        backend.enqueue(job)

    assert backend._failure_count == 1
    assert backend._open_until > 0.0

    backend._open_until = 0.0
    backend._enqueue_with_capacity.side_effect = None
    backend._enqueue_with_capacity.return_value = 1

    backend.enqueue(job)

    assert backend._failure_count == 0
    assert backend._open_until == 0.0

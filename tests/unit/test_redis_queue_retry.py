from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import redis

from AINDY.core.distributed_queue import QueueJobPayload, RedisQueueBackend


def _make_backend(**kwargs) -> RedisQueueBackend:
    client = MagicMock()
    client.register_script.return_value = MagicMock(return_value=0)

    with patch("redis.from_url", return_value=client):
        backend = RedisQueueBackend("redis://example", **kwargs)

    backend._redis = client
    return backend


def test_retries_on_connection_error():
    backend = _make_backend()
    job = QueueJobPayload(job_id="job-1", task_name="ping")

    backend._redis.lpush.side_effect = [
        redis.ConnectionError("down-1"),
        redis.ConnectionError("down-2"),
        1,
    ]

    backend.enqueue(job)

    assert backend._redis.lpush.call_count == 3
    assert backend._failure_count == 0
    assert backend._open_until == 0.0


def test_circuit_breaker_opens_after_threshold():
    backend = _make_backend(
        circuit_breaker_threshold=2,
        circuit_breaker_open_seconds=30.0,
    )
    job = QueueJobPayload(job_id="job-1", task_name="ping")

    backend._redis.lpush.side_effect = redis.ConnectionError("down")

    with pytest.raises(redis.ConnectionError):
        backend.enqueue(job)

    assert backend._redis.lpush.call_count == 3
    assert backend._failure_count == 1

    with pytest.raises(redis.ConnectionError):
        backend.enqueue(job)

    assert backend._redis.lpush.call_count == 6
    assert backend._failure_count == 2
    assert backend._open_until > 0.0

    with pytest.raises(redis.ConnectionError, match="Circuit breaker open"):
        backend.enqueue(job)

    assert backend._redis.lpush.call_count == 6


def test_circuit_breaker_resets_on_success():
    backend = _make_backend(
        circuit_breaker_threshold=1,
        circuit_breaker_open_seconds=30.0,
    )
    job = QueueJobPayload(job_id="job-1", task_name="ping")

    backend._redis.lpush.side_effect = redis.ConnectionError("down")

    with pytest.raises(redis.ConnectionError):
        backend.enqueue(job)

    assert backend._failure_count == 1
    assert backend._open_until > 0.0

    backend._open_until = 0.0
    backend._redis.lpush.side_effect = None
    backend._redis.lpush.return_value = 1

    backend.enqueue(job)

    assert backend._failure_count == 0
    assert backend._open_until == 0.0

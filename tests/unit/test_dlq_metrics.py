from __future__ import annotations

from unittest.mock import MagicMock, patch

from AINDY.core.distributed_queue import InMemoryQueueBackend, RedisQueueBackend


def test_get_dlq_depth_redis():
    client = MagicMock()
    client.register_script.return_value = MagicMock(return_value=0)
    client.llen.return_value = 7

    with patch("redis.from_url", return_value=client):
        backend = RedisQueueBackend("redis://example")

    assert backend.get_dlq_depth() == 7


def test_get_dlq_depth_inmemory():
    backend = InMemoryQueueBackend()
    for i in range(3):
        backend.fail(f"j{i}", "boom")

    assert backend.get_dlq_depth() == 3


def test_get_metrics_includes_dlq():
    backend = InMemoryQueueBackend()
    backend.fail("j1", "boom")

    metrics = backend.get_metrics()

    assert "dlq_depth" in metrics

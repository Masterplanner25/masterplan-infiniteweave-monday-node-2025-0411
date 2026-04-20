from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_inmemory_queue_rejects_burst_when_capacity_reached(monkeypatch):
    from AINDY.core.distributed_queue import InMemoryQueueBackend, QueueJobPayload, QueueSaturatedError

    monkeypatch.setenv("MAX_QUEUE_SIZE", "100")
    queue = InMemoryQueueBackend()

    accepted = 0
    rejected = 0
    for index in range(1000):
        payload = QueueJobPayload(job_id=f"job-{index}", task_name="load.test")
        try:
            queue.enqueue(payload)
            accepted += 1
        except QueueSaturatedError:
            rejected += 1

    metrics = queue.get_metrics()
    assert accepted == 100
    assert rejected == 900
    assert metrics["queue_depth"] == 100
    assert metrics["total_pending_jobs"] == 100
    assert metrics["max_queue_size"] == 100


def test_production_requires_redis_queue_backend(monkeypatch):
    from AINDY.core import distributed_queue

    distributed_queue.reset_queue()
    monkeypatch.setattr(distributed_queue, "settings", SimpleNamespace(is_prod=True, REDIS_URL=None))
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)

    with pytest.raises(RuntimeError, match="Production requires RedisQueueBackend"):
        distributed_queue.get_queue()

    distributed_queue.reset_queue()


def test_queue_saturated_error_maps_to_http_503():
    from AINDY.core.distributed_queue import QueueSaturatedError
    from AINDY.main import queue_saturated_exception_handler

    app = FastAPI()
    app.add_exception_handler(QueueSaturatedError, queue_saturated_exception_handler)

    @app.get("/enqueue")
    def _enqueue():
        raise QueueSaturatedError("queue is full", status_code=503, retry_after_seconds=7)

    client = TestClient(app)
    response = client.get("/enqueue")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "7"
    assert response.json()["error"] == "queue_saturated"


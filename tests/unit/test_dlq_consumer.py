from __future__ import annotations

import time
from collections import deque
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from AINDY.core.distributed_queue import InMemoryQueueBackend, QueueJobPayload
from AINDY.db.database import get_db
from AINDY.routes.observability_router import router
from AINDY.services.auth_service import get_current_user
from AINDY.worker import worker_loop


def _make_backend_with_dlq(count: int = 3) -> InMemoryQueueBackend:
    backend = InMemoryQueueBackend()
    for i in range(count):
        job = QueueJobPayload(job_id=f"j{i}", task_name="ping")
        backend.enqueue(job)
        backend.dequeue(timeout=1)
        backend.fail(job.job_id, f"err-{i}")
    return backend


def test_drain_dead_letters_inspect():
    backend = _make_backend_with_dlq(3)
    db = MagicMock()

    with (
        patch("AINDY.core.distributed_queue.get_queue", return_value=backend),
        patch("AINDY.platform_layer.async_job_service._emit_async_system_event"),
    ):
        result = worker_loop.drain_dead_letters(db=db, max_items=10, requeue=False)

    assert result["inspected"] == 3
    assert result["requeued"] == 0
    assert backend.get_dlq_depth() == 3


def test_drain_dead_letters_requeue():
    backend = _make_backend_with_dlq(3)
    db = MagicMock()

    with (
        patch("AINDY.core.distributed_queue.get_queue", return_value=backend),
        patch("AINDY.platform_layer.async_job_service._emit_async_system_event"),
    ):
        result = worker_loop.drain_dead_letters(db=db, max_items=10, requeue=True)

    assert result["inspected"] == 3
    assert result["requeued"] == 3
    assert backend.get_dlq_depth() == 0
    assert backend.qsize() == 3


def test_failure_rate_alert_fires():
    now = time.monotonic()
    with (
        patch.dict("os.environ", {"DLQ_ALERT_THRESHOLD": "10"}, clear=False),
        patch.object(worker_loop, "_failure_window", deque([now - 1] * 9)),
        patch.object(worker_loop.logger, "error") as mock_error,
        patch("AINDY.db.database.SessionLocal"),
    ):
        worker_loop._record_job_failure_alert(
            job_id="j1",
            operation_name="ping",
            error="boom",
        )

    mock_error.assert_called()


def test_queue_metrics_endpoint():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user-1",
        "is_admin": True,
    }
    app.dependency_overrides[get_db] = lambda: MagicMock()

    backend = InMemoryQueueBackend()
    backend.enqueue(QueueJobPayload(job_id="j1", task_name="ping"))
    backend.dequeue(timeout=1)
    backend.fail("j1", "boom")

    with (
        patch("AINDY.routes.observability_router._execute_observability", side_effect=lambda request, route_name, handler, **kwargs: handler(None)),
        patch("AINDY.core.distributed_queue.get_queue", return_value=backend),
        patch("AINDY.worker.worker_loop.get_failure_rate_stats", return_value={"failures_in_window": 2, "window_seconds": 300, "threshold": 10}),
    ):
        client = TestClient(app)
        response = client.get("/observability/queue/metrics")

    assert response.status_code == 200
    data = response.json()
    assert "dlq_depth" in data
    assert "failures_in_window" in data

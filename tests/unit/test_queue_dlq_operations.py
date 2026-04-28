from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from AINDY.core.distributed_queue import InMemoryQueueBackend, QueueJobPayload
from AINDY.routes.platform.queue_router import router
from AINDY.services.auth_service import get_current_user


def _make_backend_with_dlq(count: int = 2) -> InMemoryQueueBackend:
    backend = InMemoryQueueBackend()
    for i in range(count):
        payload = QueueJobPayload(job_id=f"job-{i}", task_name="queue.test")
        backend.enqueue(payload)
        backend.dequeue(timeout=1)
        backend.fail(payload.job_id, f"err-{i}")
    return backend


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/platform")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-1", "is_admin": True}
    return TestClient(app)


async def _fake_execute_with_pipeline(request, route_name, handler, **kwargs):
    return handler(None)


def test_remove_dead_letter_returns_true_when_job_found():
    backend = _make_backend_with_dlq(2)

    assert backend.remove_dead_letter("job-0") is True
    assert backend.get_dlq_depth() == 1
    assert all(entry["job_id"] != "job-0" for entry in backend.get_dead_letters())


def test_remove_dead_letter_returns_false_when_job_missing():
    backend = _make_backend_with_dlq(1)

    assert backend.remove_dead_letter("missing-job") is False
    assert backend.get_dlq_depth() == 1


def test_drain_dead_letters_returns_count_and_empties_dlq():
    backend = _make_backend_with_dlq(3)

    drained = backend.drain_dead_letters()

    assert drained == 3
    assert backend.get_dlq_depth() == 0
    assert backend.get_dead_letters() == []


def test_replay_endpoint_returns_404_when_job_not_found():
    client = _make_client()
    backend = _make_backend_with_dlq(1)

    with (
        patch("AINDY.routes.platform.queue_router.execute_with_pipeline", side_effect=_fake_execute_with_pipeline),
        patch("AINDY.routes.platform.queue_router.get_queue", return_value=backend),
    ):
        response = client.post("/platform/queue/dead-letters/missing-job/replay")

    assert response.status_code == 404


def test_replay_endpoint_reconstructs_and_reenqueues_payload():
    client = _make_client()
    backend = _make_backend_with_dlq(1)

    with (
        patch("AINDY.routes.platform.queue_router.execute_with_pipeline", side_effect=_fake_execute_with_pipeline),
        patch("AINDY.routes.platform.queue_router.get_queue", return_value=backend),
    ):
        response = client.post("/platform/queue/dead-letters/job-0/replay")

    assert response.status_code == 200
    assert response.json() == {"replayed": True, "job_id": "job-0"}
    assert backend.qsize() == 1
    replayed = backend.dequeue(timeout=1)
    assert replayed is not None
    assert replayed.job_id == "job-0"
    assert replayed.task_name == "queue.test"


def test_drain_endpoint_empties_dlq_and_returns_count():
    client = _make_client()
    backend = _make_backend_with_dlq(4)

    with (
        patch("AINDY.routes.platform.queue_router.execute_with_pipeline", side_effect=_fake_execute_with_pipeline),
        patch("AINDY.routes.platform.queue_router.get_queue", return_value=backend),
    ):
        response = client.post("/platform/queue/dead-letters/drain")

    assert response.status_code == 200
    assert response.json() == {"drained": 4}
    assert backend.get_dlq_depth() == 0

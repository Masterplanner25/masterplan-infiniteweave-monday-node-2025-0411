from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from AINDY.core.distributed_queue import QueueJobPayload


pytestmark = pytest.mark.redis


def _make_job(job_id: str, task_name: str = "ping") -> QueueJobPayload:
    return QueueJobPayload(
        job_id=job_id,
        task_name=task_name,
        context={"trace_id": f"trace-{job_id}"},
        retry_metadata={"attempt_count": 0, "max_attempts": 3, "is_retry": False},
    )


def test_enqueue_dequeue_basic(redis_backend):
    assert os.environ["REDIS_URL"]

    redis_backend.enqueue(_make_job("j1"))

    job = redis_backend.dequeue(timeout=1)

    assert job is not None
    assert job.job_id == "j1"

    redis_backend.ack("j1")

    assert redis_backend._redis.hlen(redis_backend._inflight_key) == 0


def test_ack_removes_from_inflight(redis_backend):
    redis_backend.enqueue(_make_job("j1"))

    job = redis_backend.dequeue(timeout=1)

    assert job is not None
    assert redis_backend._redis.hexists(redis_backend._inflight_key, "j1")

    redis_backend.ack("j1")

    assert not redis_backend._redis.hexists(redis_backend._inflight_key, "j1")


def test_fail_moves_to_dead_letter(redis_backend):
    redis_backend.enqueue(_make_job("j1"))

    job = redis_backend.dequeue(timeout=1)

    assert job is not None

    redis_backend.fail("j1", error="simulated error")

    dead_letters = [
        json.loads(entry)
        for entry in redis_backend._redis.lrange(redis_backend._dlq_key, 0, -1)
    ]

    assert len(dead_letters) == 1
    assert dead_letters[0]["job_id"] == "j1"
    assert dead_letters[0]["error"] == "simulated error"
    assert not redis_backend._redis.hexists(redis_backend._inflight_key, "j1")


def test_stale_requeue(redis_backend):
    redis_backend.enqueue(_make_job("j1"))

    job = redis_backend.dequeue(timeout=1)

    assert job is not None

    inflight = json.loads(redis_backend._redis.hget(redis_backend._inflight_key, "j1"))
    inflight["dequeued_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=5)
    ).isoformat()
    redis_backend._redis.hset(
        redis_backend._inflight_key,
        "j1",
        json.dumps(inflight),
    )

    requeued = redis_backend.requeue_stale_jobs(timeout_seconds=1)

    assert requeued == 1

    replayed = redis_backend.dequeue(timeout=1)

    assert replayed is not None
    assert replayed.job_id == "j1"


def test_delayed_enqueue(redis_backend):
    redis_backend.enqueue_delayed(_make_job("j-delayed"), delay_seconds=1)

    assert redis_backend.dequeue(timeout=0) is None

    time.sleep(1.5)
    promoted = redis_backend.process_delayed_jobs()

    assert promoted == 1

    job = redis_backend.dequeue(timeout=1)

    assert job is not None
    assert job.job_id == "j-delayed"


def test_get_metrics(redis_backend):
    redis_backend.enqueue(_make_job("j1"))
    redis_backend.enqueue(_make_job("j2"))
    redis_backend.enqueue(_make_job("j3"))

    dequeued = redis_backend.dequeue(timeout=1)

    assert dequeued is not None

    redis_backend.fail(dequeued.job_id, error="metrics failure")

    metrics = redis_backend.get_metrics()

    assert metrics["queue_depth"] == 2
    assert metrics["in_flight_count"] == 0
    assert metrics["failed_jobs"] == 1
    assert metrics["delayed_jobs"] == 0

from __future__ import annotations

import threading
import time

import pytest

from AINDY.core.distributed_queue import QueueSaturatedError
from AINDY.platform_layer import async_job_service
from AINDY.worker import worker_loop


def test_async_job_service_shutdown_drains_in_flight_and_rejects_new_jobs():
    async_job_service.start_async_job_service()
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    def _job():
        started.set()
        release.wait(2.0)
        completed.set()

    future = async_job_service._track_future(async_job_service._get_executor().submit(_job))
    assert started.wait(1.0), "job did not start"

    shutdown_done = threading.Event()

    def _shutdown():
        async_job_service.stop_async_job_service(timeout_seconds=1.5, reopen=False)
        shutdown_done.set()

    shutdown_thread = threading.Thread(target=_shutdown, daemon=True)
    shutdown_thread.start()

    deadline = time.time() + 1.0
    while async_job_service._ASYNC_ACCEPTING and time.time() < deadline:
        time.sleep(0.01)

    with pytest.raises(QueueSaturatedError, match="shutting down"):
        async_job_service.submit_async_job(
            task_name="test_task",
            payload={},
            user_id=None,
            source="test",
        )

    assert not shutdown_done.is_set(), "shutdown returned before in-flight job completed"
    release.set()
    shutdown_thread.join(timeout=2.0)

    assert completed.wait(1.0), "in-flight job did not complete before shutdown returned"
    assert future.done()
    assert shutdown_done.is_set()

    async_job_service.start_async_job_service()
    async_job_service.shutdown_async_jobs(wait=False)


def test_worker_loop_exits_cleanly_after_shutdown_signal(monkeypatch):
    worker_loop.reset_worker_state()
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    monkeypatch.setattr(worker_loop, "_run_stale_recovery", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_loop, "_run_heartbeat", lambda *args, **kwargs: None)

    def _process_one_job(_queue_backend):
        started.set()
        release.wait(2.0)
        completed.set()
        return True

    monkeypatch.setattr(worker_loop, "process_one_job", _process_one_job)

    thread = threading.Thread(
        target=worker_loop.run_worker_loop,
        kwargs={"concurrency": 1, "queue_backend": object()},
        daemon=True,
    )
    thread.start()

    assert started.wait(1.0), "worker did not start processing a job"
    worker_loop._STOP.set()
    release.set()
    thread.join(timeout=2.0)

    assert completed.wait(1.0), "worker did not finish the in-flight job"
    assert not thread.is_alive(), "worker loop did not exit after shutdown"
    worker_loop.reset_worker_state()

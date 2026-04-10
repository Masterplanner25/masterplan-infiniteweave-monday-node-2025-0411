"""
Tests for the distributed queue layer and worker loop.

Groups
------
A  QueueJobPayload — serialisation / deserialisation
B  InMemoryQueueBackend — enqueue / dequeue / ack / fail
C  get_queue() factory — backend selection
D  ExecutionDispatcher — distributed enqueue path
E  WorkerLoop — process_one_job() end-to-end

All tests use TESTING=true / InMemoryQueueBackend — no Redis required.
"""
from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

# Ensure test mode so get_queue() returns InMemoryQueueBackend.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("EXECUTION_MODE", "thread")


# ---------------------------------------------------------------------------
# A — QueueJobPayload serialisation
# ---------------------------------------------------------------------------

class TestQueueJobPayload:
    def _make(self, **kwargs):
        from core.distributed_queue import QueueJobPayload
        defaults = dict(
            job_id="job-1",
            task_name="agent.create_run",
            context={"trace_id": "t-1", "eu_id": "eu-1", "user_id": "u-1"},
            retry_metadata={"attempt_count": 0, "max_attempts": 1, "is_retry": False},
        )
        defaults.update(kwargs)
        return QueueJobPayload(**defaults)

    def test_to_json_contains_required_keys(self):
        job = self._make()
        raw = job.to_json()
        assert "job-1" in raw
        assert "agent.create_run" in raw
        assert "trace_id" in raw

    def test_round_trip(self):
        from core.distributed_queue import QueueJobPayload
        job = self._make()
        restored = QueueJobPayload.from_json(job.to_json())
        assert restored.job_id == job.job_id
        assert restored.task_name == job.task_name
        assert restored.context["trace_id"] == "t-1"
        assert restored.retry_metadata["max_attempts"] == 1

    def test_from_json_ignores_unknown_fields(self):
        import json
        from core.distributed_queue import QueueJobPayload
        raw = json.dumps({
            "job_id": "j",
            "task_name": "t",
            "context": {},
            "retry_metadata": {},
            "enqueued_at": "2026-01-01T00:00:00+00:00",
            "unknown_future_field": "value",
        })
        job = QueueJobPayload.from_json(raw)
        assert job.job_id == "j"

    def test_enqueued_at_auto_populated(self):
        from core.distributed_queue import QueueJobPayload
        job = QueueJobPayload(job_id="x", task_name="y")
        assert job.enqueued_at  # not empty


# ---------------------------------------------------------------------------
# B — InMemoryQueueBackend
# ---------------------------------------------------------------------------

class TestInMemoryQueueBackend:
    def _backend(self):
        from core.distributed_queue import InMemoryQueueBackend
        return InMemoryQueueBackend()

    def _job(self, job_id="j1", task_name="t1"):
        from core.distributed_queue import QueueJobPayload
        return QueueJobPayload(job_id=job_id, task_name=task_name)

    def test_enqueue_dequeue_roundtrip(self):
        b = self._backend()
        b.enqueue(self._job("j1", "my_task"))
        result = b.dequeue(timeout=1)
        assert result is not None
        assert result.job_id == "j1"
        assert result.task_name == "my_task"

    def test_dequeue_timeout_returns_none(self):
        b = self._backend()
        result = b.dequeue(timeout=0)
        assert result is None

    def test_fifo_ordering(self):
        b = self._backend()
        for i in range(3):
            b.enqueue(self._job(f"j{i}"))
        ids = [b.dequeue(timeout=1).job_id for _ in range(3)]
        assert ids == ["j0", "j1", "j2"]

    def test_ack_does_not_raise(self):
        b = self._backend()
        b.ack("any-id")  # no-op, must not raise

    def test_fail_does_not_raise(self):
        b = self._backend()
        b.fail("any-id", "some error")  # no-op, must not raise

    def test_qsize(self):
        b = self._backend()
        assert b.qsize() == 0
        b.enqueue(self._job())
        assert b.qsize() == 1
        b.dequeue(timeout=1)
        assert b.qsize() == 0

    def test_thread_safe_concurrent_enqueue(self):
        b = self._backend()
        results = []

        def enqueue_n():
            for i in range(20):
                b.enqueue(self._job(f"t{i}"))

        threads = [threading.Thread(target=enqueue_n) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert b.qsize() == 100


# ---------------------------------------------------------------------------
# C — get_queue() factory
# ---------------------------------------------------------------------------

class TestGetQueueFactory:
    def setup_method(self):
        from core.distributed_queue import reset_queue
        reset_queue()

    def teardown_method(self):
        from core.distributed_queue import reset_queue
        reset_queue()

    def test_returns_in_memory_when_testing(self):
        """TESTING=true (set at module top) → InMemoryQueueBackend."""
        from core.distributed_queue import InMemoryQueueBackend, get_queue
        q = get_queue()
        assert isinstance(q, InMemoryQueueBackend)

    def test_singleton_same_instance(self):
        from core.distributed_queue import get_queue
        assert get_queue() is get_queue()

    def test_force_memory_returns_fresh_instance(self):
        from core.distributed_queue import InMemoryQueueBackend, get_queue
        a = get_queue(force_memory=True)
        b = get_queue(force_memory=True)
        assert isinstance(a, InMemoryQueueBackend)
        assert a is not b  # force_memory always returns a new instance

    def test_reset_queue_clears_singleton(self):
        from core.distributed_queue import get_queue, reset_queue
        first = get_queue()
        reset_queue()
        second = get_queue()
        assert first is not second


# ---------------------------------------------------------------------------
# D — ExecutionDispatcher distributed path
# ---------------------------------------------------------------------------

class TestExecutionDispatcherDistributed:
    """Verify dispatch() routes to get_queue().enqueue() when EXECUTION_MODE=distributed."""

    def setup_method(self):
        from core.distributed_queue import InMemoryQueueBackend, reset_queue
        reset_queue()
        self._mem_q = InMemoryQueueBackend()
        os.environ["EXECUTION_MODE"] = "distributed"

    def teardown_method(self):
        from core.distributed_queue import reset_queue
        os.environ["EXECUTION_MODE"] = "thread"
        reset_queue()

    def _eu_stub(self, eu_type="job", priority="normal", eu_id=None):
        stub = MagicMock()
        stub.type = eu_type
        stub.priority = priority
        stub.id = eu_id or "eu-test-1"
        stub.extra = {"async_hint": True}  # bypass env gate
        return stub

    def test_dispatch_distributed_enqueues_job(self):
        from core.distributed_queue import reset_queue
        reset_queue()

        with patch("core.distributed_queue.get_queue", return_value=self._mem_q):
            from core.execution_dispatcher import dispatch

            eu = self._eu_stub()
            result = dispatch(
                eu,
                handler_fn=lambda: None,
                context={"log_id": "log-abc", "task_name": "agent.create_run"},
            )

        assert result.mode.value == "async"
        assert result.future is None  # no future in distributed mode
        assert self._mem_q.qsize() == 1

        job = self._mem_q.dequeue(timeout=1)
        assert job is not None
        assert job.job_id == "log-abc"
        assert job.task_name == "agent.create_run"

    def test_dispatch_thread_mode_does_not_enqueue(self):
        """EXECUTION_MODE=thread must still use ThreadPoolExecutor, not the queue."""
        os.environ["EXECUTION_MODE"] = "thread"
        from core.distributed_queue import reset_queue
        reset_queue()

        executed = threading.Event()

        with patch("core.distributed_queue.get_queue", return_value=self._mem_q):
            with patch(
                "core.execution_dispatcher.async_heavy_execution_enabled",
                return_value=False,
            ):
                from core.execution_dispatcher import dispatch

                eu = self._eu_stub()
                eu.extra = {}  # no async_hint — will use INLINE
                dispatch(eu, handler_fn=lambda: executed.set(), context={})

        # INLINE mode: handler ran immediately, queue untouched
        assert executed.is_set()
        assert self._mem_q.qsize() == 0

    def test_distributed_payload_carries_trace_context(self):
        from core.distributed_queue import reset_queue
        from utils.trace_context import set_trace_id, reset_trace_id
        reset_queue()

        tok = set_trace_id("trace-propagated-001")
        try:
            with patch("core.distributed_queue.get_queue", return_value=self._mem_q):
                from core.execution_dispatcher import dispatch

                eu = self._eu_stub()
                dispatch(
                    eu,
                    handler_fn=lambda: None,
                    context={"log_id": "log-trace-1", "task_name": "test.job"},
                )
        finally:
            reset_trace_id(tok)

        job = self._mem_q.dequeue(timeout=1)
        assert job is not None
        assert job.context["trace_id"] == "trace-propagated-001"


# ---------------------------------------------------------------------------
# E — WorkerLoop: process_one_job()
# ---------------------------------------------------------------------------

class TestWorkerLoopProcessOneJob:
    """process_one_job() with fully mocked DB and execution layers."""

    def setup_method(self):
        from core.distributed_queue import InMemoryQueueBackend, QueueJobPayload, reset_queue
        reset_queue()
        self._q = InMemoryQueueBackend()

        # Pre-load a job into the queue.
        self._q.enqueue(QueueJobPayload(
            job_id="log-worker-1",
            task_name="agent.create_run",
            context={"trace_id": "t-worker", "eu_id": "eu-w1", "user_id": "u-w1"},
            retry_metadata={"attempt_count": 0, "max_attempts": 1, "is_retry": False},
        ))

    def teardown_method(self):
        from core.distributed_queue import reset_queue
        reset_queue()

    def test_job_is_processed_and_acked(self):
        """Happy path: _try_claim_job succeeds, _execute_job runs, ack called."""
        with (
            patch("worker.worker_loop._try_claim_job", return_value=True),
            patch("worker.worker_loop._fetch_job_data", return_value=("agent.create_run", {"goal": "test"})),
            patch("platform_layer.async_job_service._execute_job") as mock_exec,
            patch("worker.worker_loop._emit_worker_event"),
        ):
            from worker.worker_loop import process_one_job

            result = process_one_job(self._q)

        assert result is True
        mock_exec.assert_called_once_with("log-worker-1", "agent.create_run", {"goal": "test"})
        assert self._q.qsize() == 0  # job consumed

    def test_returns_false_when_queue_empty(self):
        """No job available → returns False."""
        from core.distributed_queue import InMemoryQueueBackend
        from worker.worker_loop import process_one_job

        empty_q = InMemoryQueueBackend()
        result = process_one_job(empty_q)
        assert result is False

    def test_skips_already_claimed_job(self):
        """_try_claim_job returns False → ack without executing."""
        with (
            patch("worker.worker_loop._try_claim_job", return_value=False),
            patch("platform_layer.async_job_service._execute_job") as mock_exec,
            patch("worker.worker_loop._emit_worker_event"),
        ):
            from worker.worker_loop import process_one_job

            result = process_one_job(self._q)

        assert result is True
        mock_exec.assert_not_called()

    def test_skips_missing_log(self):
        """_fetch_job_data returns None → ack without executing."""
        with (
            patch("worker.worker_loop._try_claim_job", return_value=True),
            patch("worker.worker_loop._fetch_job_data", return_value=None),
            patch("platform_layer.async_job_service._execute_job") as mock_exec,
            patch("worker.worker_loop._emit_worker_event"),
        ):
            from worker.worker_loop import process_one_job

            result = process_one_job(self._q)

        assert result is True
        mock_exec.assert_not_called()

    def test_trace_context_restored_before_execution(self):
        """trace_id from job.context must be active when _execute_job runs."""
        captured_trace: list[str] = []

        def capture_exec(log_id, task_name, payload):
            from utils.trace_context import get_trace_id
            captured_trace.append(get_trace_id() or "")

        with (
            patch("worker.worker_loop._try_claim_job", return_value=True),
            patch("worker.worker_loop._fetch_job_data", return_value=("t", {})),
            patch("platform_layer.async_job_service._execute_job", side_effect=capture_exec),
            patch("worker.worker_loop._emit_worker_event"),
        ):
            from worker.worker_loop import process_one_job
            process_one_job(self._q)

        assert captured_trace == ["t-worker"]

    def test_trace_context_reset_after_job(self):
        """ContextVars must be clean after process_one_job returns."""
        with (
            patch("worker.worker_loop._try_claim_job", return_value=True),
            patch("worker.worker_loop._fetch_job_data", return_value=("t", {})),
            patch("platform_layer.async_job_service._execute_job"),
            patch("worker.worker_loop._emit_worker_event"),
        ):
            from utils.trace_context import get_trace_id
            from worker.worker_loop import process_one_job

            # Ensure no trace is set before we start.
            before = get_trace_id()
            process_one_job(self._q)
            after = get_trace_id()

        assert before == after  # context unchanged by the worker

    def test_execute_job_exception_marks_failed(self):
        """If _execute_job raises, fail() is called and True is returned."""
        acked = []
        failed = []

        class _TrackingQueue:
            def dequeue(self, timeout=5):
                from core.distributed_queue import QueueJobPayload
                return QueueJobPayload(
                    job_id="fail-job",
                    task_name="boom",
                    context={"trace_id": "t-fail"},
                )

            def ack(self, job_id):
                acked.append(job_id)

            def fail(self, job_id, error=""):
                failed.append(job_id)

        with (
            patch("worker.worker_loop._try_claim_job", return_value=True),
            patch("worker.worker_loop._fetch_job_data", return_value=("boom", {})),
            patch("platform_layer.async_job_service._execute_job", side_effect=RuntimeError("boom")),
            patch("worker.worker_loop._emit_worker_event"),
        ):
            from worker.worker_loop import process_one_job
            result = process_one_job(_TrackingQueue())

        assert result is True
        assert "fail-job" in failed
        assert "fail-job" not in acked

    def test_observability_events_emitted(self):
        """job_started and job_completed events are emitted for a happy-path job."""
        emitted_types: list[str] = []

        def capture_emit(event_type, **kwargs):
            emitted_types.append(event_type)

        with (
            patch("worker.worker_loop._try_claim_job", return_value=True),
            patch("worker.worker_loop._fetch_job_data", return_value=("t", {})),
            patch("platform_layer.async_job_service._execute_job"),
            patch("worker.worker_loop._emit_worker_event", side_effect=capture_emit),
        ):
            from worker.worker_loop import process_one_job
            process_one_job(self._q)

        assert "job_started" in emitted_types
        assert "job_completed" in emitted_types


# ---------------------------------------------------------------------------
# F — Backward compatibility: thread mode still works
# ---------------------------------------------------------------------------

class TestThreadModeBackwardCompat:
    """EXECUTION_MODE=thread (default) must behave exactly as before."""

    def test_inline_execution_unchanged(self):
        """eu.type=task + async disabled → INLINE, handler runs on caller thread."""
        from core.execution_dispatcher import ExecutionMode, dispatch

        ran = []

        class _Stub:
            type = "task"
            priority = "normal"
            id = "eu-inline"
            extra = {}

        with patch(
            "core.execution_dispatcher.async_heavy_execution_enabled",
            return_value=False,
        ):
            result = dispatch(_Stub(), handler_fn=lambda: ran.append(1) or {"ok": True})

        assert result.mode is ExecutionMode.INLINE
        assert result.envelope == {"ok": True}
        assert ran == [1]

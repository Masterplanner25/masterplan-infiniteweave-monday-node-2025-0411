from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

from AINDY.config import settings

logger = logging.getLogger(__name__)


def _increment_drop_metrics() -> None:
    try:
        from AINDY.platform_layer.metrics import memory_ingest_dropped_total

        memory_ingest_dropped_total.inc()
    except Exception:
        pass


def _set_queue_metrics(*, depth: int, capacity: int) -> None:
    try:
        from AINDY.platform_layer.metrics import (
            memory_ingest_queue_capacity,
            memory_ingest_queue_depth,
        )

        memory_ingest_queue_depth.set(depth)
        memory_ingest_queue_capacity.set(capacity)
    except Exception:
        pass


class MemoryIngestQueue:
    """Bounded queue that decouples memory write callers from the DB write path."""

    def __init__(
        self,
        maxsize: int,
        worker_handler: Callable[[Any], None] | None = None,
        *,
        poll_interval: float = 0.25,
    ):
        if int(maxsize) <= 0:
            raise ValueError("MemoryIngestQueue maxsize must be greater than zero")
        self.maxsize = int(maxsize)
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=self.maxsize)
        self._worker_handler = worker_handler
        self._poll_interval = max(0.05, float(poll_interval))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._accepting = True
        self._dropped_total = 0
        self._lock = threading.Lock()
        self._update_metrics()

    def set_worker_handler(self, worker_handler: Callable[[Any], None]) -> None:
        self._worker_handler = worker_handler

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._accepting = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self.worker_loop,
                name="memory-ingest-queue",
                daemon=True,
            )
            self._thread.start()
        logger.info(
            "[MemoryIngestQueue] Worker started (capacity=%s)",
            self.maxsize,
        )

    def stop(self, timeout: float = 10.0, *, drain: bool = True) -> None:
        self._accepting = False
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        abandoned_depth = self.depth
        if drain and abandoned_depth > 0 and not (thread and thread.is_alive()):
            # Best-effort synchronous drain after the background worker has exited.
            while not (thread and thread.is_alive()) and self._process_one(block=False):
                pass
            abandoned_depth = self.depth
        if thread is not None and thread.is_alive():
            logger.warning(
                "[MemoryIngestQueue] Shutdown timed out with %s queued write(s) still pending",
                self.depth,
            )
        elif abandoned_depth > 0:
            logger.warning(
                "[MemoryIngestQueue] Shutdown completed with %s queued write(s) abandoned",
                abandoned_depth,
            )
        self._thread = None
        self._update_metrics()
        logger.info(
            "[MemoryIngestQueue] Worker stopped (depth=%s dropped_total=%s)",
            self.depth,
            self._dropped_total,
        )

    def enqueue(self, ingest_payload: Any) -> bool:
        """
        Attempt to enqueue a memory write.
        Returns True if accepted, False if the queue is full.
        Never blocks. Never raises on full queue.
        """
        if not self._accepting:
            self._dropped_total += 1
            _increment_drop_metrics()
            self._update_metrics()
            return False
        try:
            self._queue.put_nowait(ingest_payload)
            self._update_metrics()
            return True
        except queue.Full:
            self._dropped_total += 1
            _increment_drop_metrics()
            self._update_metrics()
            return False

    def worker_loop(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            self._process_one(block=True)

    def _process_one(self, *, block: bool) -> bool:
        try:
            payload = (
                self._queue.get(timeout=self._poll_interval)
                if block
                else self._queue.get_nowait()
            )
        except queue.Empty:
            self._update_metrics()
            return False

        try:
            if self._worker_handler is None:
                logger.warning("[MemoryIngestQueue] No worker handler configured; dropping queued payload")
            else:
                self._worker_handler(payload)
        except Exception as exc:
            logger.warning("[MemoryIngestQueue] DB write failed: %s", exc)
        finally:
            self._queue.task_done()
            self._update_metrics()
        return True

    @property
    def depth(self) -> int:
        return int(self._queue.qsize())

    @property
    def dropped_total(self) -> int:
        return int(self._dropped_total)

    def snapshot(self) -> dict[str, int | bool]:
        return {
            "depth": self.depth,
            "capacity": self.maxsize,
            "dropped_total": self.dropped_total,
            "worker_running": bool(self._thread and self._thread.is_alive()),
        }

    def _update_metrics(self) -> None:
        _set_queue_metrics(depth=self.depth, capacity=self.maxsize)


_memory_ingest_queue: MemoryIngestQueue | None = None
_memory_ingest_queue_lock = threading.Lock()


def get_memory_ingest_queue() -> MemoryIngestQueue:
    global _memory_ingest_queue
    if _memory_ingest_queue is None:
        with _memory_ingest_queue_lock:
            if _memory_ingest_queue is None:
                _memory_ingest_queue = MemoryIngestQueue(
                    maxsize=settings.AINDY_MEMORY_INGEST_QUEUE_MAX,
                )
    return _memory_ingest_queue

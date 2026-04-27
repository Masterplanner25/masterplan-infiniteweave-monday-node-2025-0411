from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import insert

logger = logging.getLogger(__name__)

_QUEUE_MAX = 10_000
_FLUSH_INTERVAL = 5.0
_BATCH_SIZE = 200


@dataclass
class PendingMetric:
    request_id: str
    trace_id: str
    user_id: Optional[object]
    method: str
    path: str
    status_code: int
    duration_ms: float
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RequestMetricWriter:
    """Thread-safe non-blocking background writer for RequestMetric rows."""

    def __init__(self) -> None:
        self._queue: queue.Queue[PendingMetric] = queue.Queue(maxsize=_QUEUE_MAX)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dropped = 0
        self._last_flush_monotonic = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_flush_monotonic = 0.0
        self._thread = threading.Thread(
            target=self._run,
            name="request-metric-writer",
            daemon=True,
        )
        self._thread.start()
        logger.info("[request_metric_writer] Background writer started.")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        while not self._queue.empty():
            self._flush()
        logger.info("[request_metric_writer] Background writer stopped.")

    def enqueue(self, metric: PendingMetric) -> bool:
        try:
            self._queue.put_nowait(metric)
            return True
        except queue.Full:
            self._dropped += 1
            try:
                from AINDY.platform_layer.metrics import request_metric_drops_total

                request_metric_drops_total.inc()
            except Exception:
                pass
            if self._dropped % 100 == 1:
                logger.warning(
                    "[request_metric_writer] Queue full; dropped %d metrics",
                    self._dropped,
                )
            return False

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_FLUSH_INTERVAL)
            self._flush()

    def _flush(self) -> None:
        batch: list[PendingMetric] = []
        try:
            while len(batch) < _BATCH_SIZE:
                batch.append(self._queue.get_nowait())
        except queue.Empty:
            pass

        if not batch:
            return

        from AINDY.db.database import SessionLocal
        from AINDY.db.models.request_metric import RequestMetric

        mappings = [
            {
                "request_id": metric.request_id,
                "trace_id": metric.trace_id,
                "user_id": metric.user_id,
                "method": metric.method,
                "path": metric.path,
                "status_code": metric.status_code,
                "duration_ms": metric.duration_ms,
                "created_at": metric.created_at,
            }
            for metric in batch
        ]

        db = None
        try:
            db = SessionLocal()
            db.execute(insert(RequestMetric), mappings)
            db.commit()
            self._last_flush_monotonic = time.monotonic()
        except Exception as exc:
            logger.warning(
                "[request_metric_writer] Batch flush failed (%d rows): %s",
                len(batch),
                exc,
            )
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    def snapshot(self) -> dict[str, int | bool | float]:
        return {
            "queue_depth": int(self._queue.qsize()),
            "dropped_total": int(self._dropped),
            "worker_running": bool(self._thread and self._thread.is_alive()),
            "last_flush_monotonic": float(self._last_flush_monotonic),
        }


_writer: Optional[RequestMetricWriter] = None
_writer_lock = threading.Lock()


def get_writer() -> RequestMetricWriter:
    global _writer
    if _writer is None:
        with _writer_lock:
            if _writer is None:
                _writer = RequestMetricWriter()
    return _writer

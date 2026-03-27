"""
signal_emitter.py — Batched HTTP signal emitter for A.I.N.D.Y. Watcher.

Enqueues SessionEvents into a thread-safe deque and flushes them in a
background thread via POST to the A.I.N.D.Y. API.

Contract:
  - emit() NEVER blocks the caller — always returns immediately
  - emit() NEVER raises — silently drops on queue overflow
  - Flush failures are retried with exponential backoff (max 3 attempts)
  - DRY_RUN=true logs signals instead of sending HTTP requests
  - start()/stop() manage the background flush thread lifecycle
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict
from typing import List, Optional

from services.external_call_service import perform_external_call
from watcher.session_tracker import SessionEvent

logger = logging.getLogger(__name__)

_DEFAULT_FLUSH_INTERVAL = 10.0   # seconds between flush cycles
_DEFAULT_BATCH_SIZE = 20         # max signals per POST request
_DEFAULT_MAX_QUEUE = 500         # drop oldest when queue exceeds this
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0          # seconds; doubled per retry


class SignalEmitter:
    """
    Thread-safe signal emitter with batched HTTP delivery.

    Parameters
    ----------
    api_url : str
        Full URL for POST /watcher/signals (e.g. http://localhost:8000/watcher/signals)
    api_key : str
        Value for X-API-Key header.
    flush_interval : float
        Seconds between flush attempts.
    batch_size : int
        Maximum signals per HTTP request.
    max_queue : int
        Maximum buffered signals. Oldest are dropped on overflow.
    dry_run : bool
        When True, logs signals rather than sending HTTP requests.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        flush_interval: float = _DEFAULT_FLUSH_INTERVAL,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        max_queue: int = _DEFAULT_MAX_QUEUE,
        dry_run: bool = False,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._max_queue = max_queue
        self._dry_run = dry_run

        self._queue: deque[SessionEvent] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background flush thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._flush_loop,
            name="aindy-watcher-emitter",
            daemon=True,
        )
        self._thread.start()
        logger.info("SignalEmitter started (dry_run=%s, url=%s)", self._dry_run, self._api_url)

    def stop(self, drain_timeout: float = 5.0) -> None:
        """Signal flush thread to stop; flush remaining signals before exit."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=drain_timeout)
        # Final flush
        self._flush_batch(drain=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit(self, event: SessionEvent) -> None:
        """
        Enqueue a signal for delivery. Non-blocking, never raises.
        Drops the oldest signal if queue is full.
        """
        try:
            with self._lock:
                if len(self._queue) >= self._max_queue:
                    self._queue.popleft()  # drop oldest
                self._queue.append(event)
        except Exception as exc:
            logger.debug("SignalEmitter.emit() swallowed exception: %s", exc)

    def emit_many(self, events: List[SessionEvent]) -> None:
        """Emit a list of events."""
        for event in events:
            self.emit(event)

    # ------------------------------------------------------------------
    # Background flush loop
    # ------------------------------------------------------------------

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._flush_interval)
            self._flush_batch()

    def _flush_batch(self, drain: bool = False) -> None:
        """Drain up to batch_size signals and POST them."""
        while True:
            batch: List[SessionEvent] = []
            with self._lock:
                while self._queue and len(batch) < self._batch_size:
                    batch.append(self._queue.popleft())

            if not batch:
                break

            self._send_with_retry(batch)

            # In normal (non-drain) mode, send one batch per flush cycle
            if not drain:
                break

    def _send_with_retry(self, batch: List[SessionEvent]) -> None:
        """Send a batch with exponential backoff retry. Never raises."""
        if self._dry_run:
            for event in batch:
                logger.info(
                    "[DRY RUN] signal: %s | session=%s | app=%s | title=%s",
                    event.signal_type,
                    event.session_id,
                    event.app_name,
                    event.window_title,
                )
            return

        payload = [asdict(e) for e in batch]
        delay = _RETRY_BASE_DELAY

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                import httpx
                with httpx.Client(timeout=10.0) as client:
                    resp = perform_external_call(
                        service_name="watcher",
                        endpoint=self._api_url,
                        method="POST",
                        extra={
                            "purpose": "watcher_signal_emit",
                            "batch_size": len(batch),
                        },
                        operation=lambda: client.post(
                            self._api_url,
                            json={"signals": payload},
                            headers={"X-API-Key": self._api_key},
                        ),
                    )
                if resp.status_code < 400:
                    logger.debug(
                        "Emitted %d signals (status=%d)", len(batch), resp.status_code
                    )
                    return
                logger.warning(
                    "Watcher signal POST failed (attempt=%d status=%d): %s",
                    attempt,
                    resp.status_code,
                    resp.text[:200],
                )
            except Exception as exc:
                logger.warning(
                    "Watcher signal POST exception (attempt=%d): %s", attempt, exc
                )

            if attempt < _MAX_RETRIES:
                time.sleep(delay)
                delay *= 2

        logger.error(
            "Dropped %d signals after %d failed attempts", len(batch), _MAX_RETRIES
        )

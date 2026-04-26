"""
Distributed Event Bus — Redis pub/sub for cross-instance scheduler events.

Problem solved
--------------
SchedulerEngine._waiting is per-process in-memory.  When a flow enters WAIT
on Instance A and the resume event is received by Instance B, B's local
notify_event() finds no matching entry and the flow stays stuck forever.

Solution
--------
Every notify_event() call publishes a JSON payload to a shared Redis channel.
All instances subscribe to that channel and call their own local
notify_event(broadcast=False) when a message arrives.  Because every instance
re-registers all "waiting" callbacks during startup rehydration, any instance
can now resume any waiting flow regardless of which instance originally
registered the WAIT.

Infinite-loop prevention
------------------------
The published payload includes ``source_instance_id``.  Subscribers skip
messages whose source matches their own instance ID — the originating
instance's local notify_event() already ran before publish.

Duplicate execution prevention
-------------------------------
Unchanged.  The DB-level FlowRun claim (``UPDATE WHERE status='waiting'``)
is the authoritative gatekeeper.  Even if multiple instances receive the
broadcast and all call their local notify_event(), the atomic claim ensures
exactly one instance proceeds.

Fault tolerance
---------------
- Redis unavailable: publish() returns False and logs a WARNING; local-only
  behaviour is preserved.  No exception propagates to the caller.
- Subscriber thread crash: caught by the outer reconnect loop; reconnects
  with exponential back-off (1 s → 30 s cap).
- ``AINDY_EVENT_BUS_ENABLED=false``: bus is completely disabled; system
  behaves as before (single-instance mode).

Configuration (environment variables)
--------------------------------------
  AINDY_REDIS_URL          Redis connection URL (default: redis://localhost:6379/0)
  AINDY_EVENT_BUS_CHANNEL  Pub/sub channel name  (default: aindy:scheduler_events)
  AINDY_EVENT_BUS_ENABLED  "false" / "0" / "no" to disable (default: enabled)

Usage
-----
    # Publisher (automatic — called inside notify_event())
    from AINDY.kernel.event_bus import get_event_bus
    get_event_bus().publish("operation.completed", correlation_id="chain-abc")

    # Subscriber (called once at startup on every instance)
    get_event_bus().start_subscriber()
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

REDIS_URL: str = os.getenv("AINDY_REDIS_URL", "redis://localhost:6379/0")
CHANNEL: str = os.getenv("AINDY_EVENT_BUS_CHANNEL", "aindy:scheduler_events")
ENABLED: bool = os.getenv("AINDY_EVENT_BUS_ENABLED", "true").lower() not in {
    "0", "false", "no", "off",
}

_RECONNECT_BASE_DELAY: float = 1.0    # seconds before first reconnect attempt
_RECONNECT_MAX_DELAY: float = 30.0   # cap for exponential back-off
_MAX_BUFFER_SIZE: int = 1000         # max events to buffer before rehydration
_STATUS_REDIS_TIMEOUT: float = 0.5


def _get_instance_id() -> str:
    """Stable identifier for this OS process/pod."""
    return (
        os.environ.get("INSTANCE_ID")
        or os.environ.get("HOSTNAME")
        or socket.gethostname()
        or "unknown-instance"
    )


# ── EventBus ──────────────────────────────────────────────────────────────────

class EventBus:
    """
    Thin, non-fatal wrapper around Redis pub/sub.

    Publisher
    ---------
    ``publish(event_type, correlation_id)`` is called by ``notify_event()``
    after the local ``_waiting`` scan has already run.  It serialises the
    event to JSON and pushes it to the shared Redis channel.

    Subscriber
    ----------
    ``start_subscriber()`` spawns a single daemon thread that blocks on
    ``pubsub.listen()``.  On each message it calls the local
    ``SchedulerEngine.notify_event(broadcast=False)`` to wake any locally
    registered waiter.  Messages from the same instance are silently skipped.

    Thread safety
    -------------
    ``publish()`` creates a fresh Redis client per ``EventBus`` instance and
    is protected against client-reset races by the ``_pub_lock``.  The
    subscriber runs in its own thread with its own Redis connection.
    """

    def __init__(self) -> None:
        self._instance_id: str = _get_instance_id()
        self._enabled: bool = ENABLED
        self._pub_lock = threading.Lock()
        self._pub_client = None          # lazy Redis client for publishing
        self._subscriber_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._consecutive_failures: int = 0
        self._max_failures: int = 3      # disable after 3 consecutive failures
        # Pre-rehydration buffer: events received before _waiting is populated
        self._pre_rehydration_buffer: list[tuple[str, str | None]] = []
        self._buffer_lock = threading.Lock()

    # ── Publisher ─────────────────────────────────────────────────────────────

    def _get_pub_client(self):
        """Return (or lazily create) the publish-side Redis client."""
        if self._pub_client is None:
            import redis as _redis  # noqa: PLC0415 — lazy; redis may not be installed
            self._pub_client = _redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        return self._pub_client

    def publish(self, event_type: str, *, correlation_id: str | None = None) -> bool:
        """
        Publish *event_type* to all instances via Redis pub/sub.

        Called automatically by ``SchedulerEngine.notify_event()`` after the
        local scan completes.  Never raises — returns ``False`` on any error.

        Args:
            event_type:     The event name (e.g. ``"operation.completed"``).
            correlation_id: Optional correlation chain ID forwarded to
                            remote ``notify_event()`` calls.

        Returns:
            ``True`` if the message was delivered to Redis, ``False`` on any
            failure (Redis down, serialisation error, etc.).
        """
        if not self._enabled:
            return False

        payload = json.dumps({
            "event_type": event_type,
            "correlation_id": correlation_id,
            "source_instance_id": self._instance_id,
        })

        with self._pub_lock:
            try:
                client = self._get_pub_client()
                client.publish(CHANNEL, payload)
                logger.debug(
                    "[EventBus] published event=%r corr=%r channel=%s",
                    event_type, correlation_id, CHANNEL,
                )
                self._consecutive_failures = 0
                return True
            except Exception as exc:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._max_failures:
                    self._enabled = False
                    logger.warning(
                        "[EventBus] disabled after %d consecutive failures — Redis unavailable. "
                        "Set AINDY_EVENT_BUS_ENABLED=false to suppress this.",
                        self._consecutive_failures,
                    )
                else:
                    logger.warning(
                        "[EventBus] WAIT/RESUME event %r could NOT be propagated to other "
                        "instances (Redis unavailable). Flows waiting on other instances "
                        "will not be resumed. correlation_id=%s error=%s",
                        event_type, correlation_id, exc,
                    )
                # Reset client so the next call gets a fresh connection.
                self._pub_client = None
                return False

    def _is_subscriber_running(self) -> bool:
        thread = self._subscriber_thread
        return bool(thread is not None and thread.is_alive())

    def _is_redis_connected(self) -> bool:
        if not self._enabled:
            return False
        try:
            if self._pub_client is not None:
                self._pub_client.ping()
                return True

            import redis as _redis  # noqa: PLC0415

            client = _redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=_STATUS_REDIS_TIMEOUT,
                socket_timeout=_STATUS_REDIS_TIMEOUT,
            )
            client.ping()
            return True
        except Exception:
            return False

    def _get_propagation_mode(self) -> str:
        """Return the current event propagation mode."""
        if not self._enabled:
            return "disabled"
        if self._is_redis_connected() and self._is_subscriber_running():
            return "cross-instance"
        return "local-only"

    def get_status(self) -> dict:
        """Return the current operational status of the event bus."""
        try:
            enabled = bool(self._enabled)
            subscriber_running = self._is_subscriber_running()
            redis_connected = self._is_redis_connected()
            mode = self._get_propagation_mode()
            return {
                "enabled": enabled,
                "subscriber_running": subscriber_running,
                "redis_connected": redis_connected,
                "mode": mode,
            }
        except Exception:
            return {
                "enabled": False,
                "subscriber_running": False,
                "redis_connected": False,
                "mode": "unknown",
            }

    # ── Subscriber ────────────────────────────────────────────────────────────

    def start_subscriber(self) -> None:
        """
        Start the background subscriber daemon thread (idempotent).

        Safe to call multiple times — only one thread is ever started.
        No-op when the event bus is disabled.

        Must be called at application startup on EVERY instance, before
        rehydration completes, so the thread is ready to receive events as
        soon as the first resume event fires.
        """
        if not self._enabled:
            logger.info(
                "[EventBus] disabled (AINDY_EVENT_BUS_ENABLED=false) "
                "— subscriber not started; operating in local-only mode"
            )
            return

        if self._subscriber_thread is not None and self._subscriber_thread.is_alive():
            logger.debug("[EventBus] subscriber already running — skipping duplicate start")
            return

        self._stop_event.clear()
        self._subscriber_thread = threading.Thread(
            target=self._subscriber_loop,
            name="aindy-event-bus-subscriber",
            daemon=True,   # exits when the main process exits
        )
        self._subscriber_thread.start()
        logger.info(
            "[EventBus] subscriber started (instance=%s channel=%s)",
            self._instance_id, CHANNEL,
        )

    def stop_subscriber(self) -> None:
        """Signal the subscriber thread to exit on its next iteration.

        Non-blocking.  Called during graceful shutdown.
        """
        self._stop_event.set()

    def stop(self, timeout: float | None = None) -> None:
        """Stop the subscriber thread and close publish-side state."""
        self._stop_event.set()
        thread = self._subscriber_thread
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("[EventBus] subscriber did not stop within timeout")
        self._subscriber_thread = None
        self._pub_client = None

    def _subscriber_loop(self) -> None:
        """
        Daemon loop: connect → subscribe → dispatch messages → reconnect.

        Reconnects with exponential back-off capped at
        ``_RECONNECT_MAX_DELAY`` seconds.  Stops cleanly when
        ``_stop_event`` is set.
        """
        import redis as _redis  # noqa: PLC0415

        delay = _RECONNECT_BASE_DELAY

        while not self._stop_event.is_set():
            try:
                r = _redis.from_url(REDIS_URL, decode_responses=True)
                pubsub = r.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(CHANNEL)
                logger.info(
                    "[EventBus] subscribed to channel=%s instance=%s",
                    CHANNEL, self._instance_id,
                )
                delay = _RECONNECT_BASE_DELAY  # reset on successful connect

                for message in pubsub.listen():
                    if self._stop_event.is_set():
                        break
                    if message is None or message.get("type") != "message":
                        continue
                    self._handle_message(message.get("data", ""))

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "[EventBus] subscriber lost connection (%s) "
                    "— reconnecting in %.1fs",
                    exc, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX_DELAY)

        logger.info("[EventBus] subscriber stopped (instance=%s)", self._instance_id)

    def _handle_message(self, data: str) -> None:
        """
        Dispatch a single pub/sub message to the local SchedulerEngine.

        Skips malformed payloads and messages originating from this instance
        (the originating instance already ran its local notify_event()).
        """
        # ── Parse ─────────────────────────────────────────────────────────────
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            logger.debug(
                "[EventBus] malformed message ignored: %r", data
            )
            return

        # ── Source filter — skip own-instance messages ─────────────────────
        source = payload.get("source_instance_id")
        if source == self._instance_id:
            logger.debug(
                "[EventBus] skipping own-instance message event=%r",
                payload.get("event_type"),
            )
            return

        # ── Validate payload ───────────────────────────────────────────────
        event_type = payload.get("event_type")
        if not event_type or not isinstance(event_type, str):
            logger.debug(
                "[EventBus] message missing event_type — ignored: %r", payload
            )
            return

        correlation_id: str | None = payload.get("correlation_id") or None

        logger.debug(
            "[EventBus] received event=%r corr=%r from=%s",
            event_type, correlation_id, source,
        )

        # ── Local notify (broadcast=False prevents re-publication) ─────────
        try:
            from AINDY.kernel.scheduler_engine import get_scheduler_engine  # noqa: PLC0415
            engine = get_scheduler_engine()
            if not engine.is_rehydrated():
                # Buffer event until _waiting dict is fully populated
                with self._buffer_lock:
                    if len(self._pre_rehydration_buffer) < _MAX_BUFFER_SIZE:
                        self._pre_rehydration_buffer.append((event_type, correlation_id))
                        logger.debug(
                            "[EventBus] buffered pre-rehydration event=%r (buffer=%d)",
                            event_type, len(self._pre_rehydration_buffer),
                        )
                    else:
                        logger.warning(
                            "[EventBus] pre-rehydration buffer full (%d); dropping event=%r",
                            _MAX_BUFFER_SIZE, event_type,
                        )
                return
            engine.notify_event(
                event_type,
                correlation_id=correlation_id,
                broadcast=False,  # already broadcasting — suppress re-publish
            )
        except Exception as exc:
            logger.warning(
                "[EventBus] local notify_event failed for event=%r (non-fatal): %s",
                event_type, exc,
            )


    def drain_buffered_events(self) -> int:
        """
        Dispatch all events buffered before rehydration completed.

        Called once by startup after ``mark_rehydration_complete()``.  Safe to
        call multiple times — second call finds an empty buffer and returns 0.

        Returns:
            Number of events drained and dispatched.
        """
        with self._buffer_lock:
            pending = self._pre_rehydration_buffer[:]
            self._pre_rehydration_buffer.clear()

        if not pending:
            return 0

        logger.info("[EventBus] draining %d buffered pre-rehydration event(s)", len(pending))
        from AINDY.kernel.scheduler_engine import get_scheduler_engine  # noqa: PLC0415
        engine = get_scheduler_engine()
        dispatched = 0
        for event_type, correlation_id in pending:
            try:
                engine.notify_event(
                    event_type,
                    correlation_id=correlation_id,
                    broadcast=False,
                )
                dispatched += 1
            except Exception as exc:
                logger.warning(
                    "[EventBus] drain: notify_event failed for event=%r (non-fatal): %s",
                    event_type, exc,
                )
        logger.info("[EventBus] drained %d/%d buffered event(s)", dispatched, len(pending))
        return dispatched


# ── Module-level singleton ────────────────────────────────────────────────────

_EVENT_BUS: EventBus | None = None
_BUS_LOCK = threading.Lock()


def get_event_bus() -> EventBus:
    """Return the process-level EventBus singleton.

    Thread-safe double-checked locking.  Tests should construct
    ``EventBus()`` directly for isolation.
    """
    global _EVENT_BUS
    if _EVENT_BUS is None:
        with _BUS_LOCK:
            if _EVENT_BUS is None:
                _EVENT_BUS = EventBus()
    return _EVENT_BUS


def get_redis_client():
    """Return a Redis client for auxiliary wait-registry operations, or None."""
    configured_url = os.getenv("AINDY_REDIS_URL")
    if not ENABLED or not configured_url:
        return None
    try:
        import redis as _redis  # noqa: PLC0415

        return _redis.from_url(
            configured_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    except Exception:
        logger.debug("[EventBus] auxiliary Redis client unavailable", exc_info=True)
        return None


# ── Public API — single entry point for all event emission ───────────────────

def publish_event(
    event_type: str,
    *,
    correlation_id: str | None = None,
) -> int:
    """Emit *event_type* through the full distributed path.

    This is the **only** function that should be called to trigger resume
    events.  No production code should call ``notify_event()`` directly.

    Execution path
    --------------
    1. ``SchedulerEngine.notify_event(broadcast=True)``

       a. Scans the local ``_waiting`` dict and re-enqueues any matched runs
          on *this* instance (immediate, synchronous).

       b. Publishes ``{event_type, correlation_id, source_instance_id}`` to
          the Redis channel so every other instance receives the broadcast.

    2. Each remote subscriber receives the message and calls
       ``notify_event(broadcast=False)`` on its own local scheduler, waking
       flows registered there.

    Non-fatal: if Redis is unavailable, step 1a still runs and matched flows
    on the current instance are resumed normally.

    Args:
        event_type:     The event name (e.g. ``"operation.completed"``).
        correlation_id: Optional correlation chain ID forwarded to all
                        remote ``notify_event()`` calls.

    Returns:
        Number of flows re-enqueued **locally** on this instance.
        Remote resume counts are not returned (fire-and-forget via Redis).
    """
    from AINDY.kernel.scheduler_engine import get_scheduler_engine  # noqa: PLC0415
    return get_scheduler_engine().notify_event(
        event_type,
        correlation_id=correlation_id,
        broadcast=True,
    )

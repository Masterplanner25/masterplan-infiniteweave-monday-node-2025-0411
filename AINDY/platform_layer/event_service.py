"""
event_service.py â€” External webhook subscriptions for SystemEvents.

External systems POST to /platform/webhooks to subscribe to one or more
event types.  Whenever a matching SystemEvent is emitted, A.I.N.D.Y.
dispatches an HTTPS POST to the registered callback URL.

Subscription matching:
  "execution.completed"   â€” exact match
  "execution.*"           â€” prefix wildcard (any event starting with "execution.")
  "*"                     â€” global wildcard (every event)

Delivery:
  - Dispatched in a background daemon thread â€” never blocks the event path.
  - Up to 3 attempts with exponential back-off: 1 s â†’ 2 s â†’ 4 s.
  - Per-attempt timeout: 10 seconds.
  - Requests are HMAC-SHA256 signed when a secret is configured
    (X-AINDY-Signature: sha256=<hex>).
  - All delivery failures are logged and swallowed â€” a failing webhook
    never affects event persistence or the flow that emitted the event.

Thread safety:
  _webhook_lock protects writes to _SUBSCRIPTIONS.
  ThreadPoolExecutor caps the maximum number of concurrent delivery threads.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_webhook_lock = threading.Lock()

# subscription_id â†’ metadata dict
_SUBSCRIPTIONS: dict[str, dict[str, Any]] = {}

_INTERNAL_HANDLERS: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}

# Bounded pool â€” prevents thread explosion under bursts of events
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="aindy-webhook")

# Delivery tuning
_MAX_ATTEMPTS = 3
_BASE_BACKOFF_SECONDS = 1.0   # doubles on each retry: 1 s, 2 s, 4 s
_ATTEMPT_TIMEOUT = 10         # seconds per HTTP attempt


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _matches(pattern: str, event_type: str) -> bool:
    """
    Return True if event_type satisfies pattern.

    "*"            â€” matches everything
    "execution.*"  â€” matches any event whose type starts with "execution."
    exact string   â€” case-sensitive equality
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-1]   # "execution." from "execution.*"
        return event_type.startswith(prefix)
    return pattern == event_type


# ---------------------------------------------------------------------------
# Internal event handlers
# ---------------------------------------------------------------------------

def register_event_handler(
    event_type: str,
    handler: Callable[[dict[str, Any]], Any],
) -> None:
    """Register an in-process handler for a SystemEvent type or wildcard."""
    if not event_type or not event_type.strip():
        raise ValueError("event_type must be a non-empty string")
    if not callable(handler):
        raise ValueError("handler must be callable")
    with _webhook_lock:
        handlers = _INTERNAL_HANDLERS.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)


def dispatch_internal_event_handlers(
    *,
    db: Session | None,
    event_type: str,
    event_id: str,
    payload: dict[str, Any],
    user_id: str | None,
    trace_id: str | None,
    source: str | None,
) -> int:
    """Dispatch a SystemEvent to registered in-process handlers."""
    with _webhook_lock:
        handlers = [
            handler
            for pattern, pattern_handlers in _INTERNAL_HANDLERS.items()
            if _matches(pattern, event_type)
            for handler in pattern_handlers
        ]

    if not handlers:
        return 0

    event = {
        "event_id": event_id,
        "event_type": event_type,
        "payload": payload or {},
        "user_id": user_id,
        "trace_id": trace_id,
        "source": source,
        "db": db,
    }
    dispatched = 0
    for handler in handlers:
        try:
            handler(event)
            dispatched += 1
        except Exception as exc:
            logger.warning(
                "internal event handler failed: event=%s handler=%s error=%s",
                event_type,
                getattr(handler, "__name__", repr(handler)),
                exc,
            )
    return dispatched


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def subscribe_webhook(
    event_type: str,
    callback_url: str,
    *,
    secret: str | None = None,
    user_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Register a new webhook subscription.

    If *db* is provided the subscription is persisted to webhook_subscriptions
    so it survives restarts.  Pass db=None when called from the startup loader.

    Returns the stored metadata dict including the generated subscription_id.
    Raises ValueError on invalid input.
    """
    if not event_type or not event_type.strip():
        raise ValueError("event_type must be a non-empty string")
    if not callback_url or not (
        callback_url.startswith("http://") or callback_url.startswith("https://")
    ):
        raise ValueError(
            f"callback_url must be an http:// or https:// URL, got {callback_url!r}"
        )

    subscription_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    meta: dict[str, Any] = {
        "id": subscription_id,
        "event_type": event_type,
        "callback_url": callback_url,
        "signed": secret is not None,
        "_secret": secret,           # stored but excluded from list/get responses
        "created_at": now.isoformat(),
        "created_by": user_id,
        "delivery_attempts": 0,
        "delivery_successes": 0,
        "delivery_failures": 0,
        "last_delivered_at": None,
        "last_status": None,
    }
    with _webhook_lock:
        _SUBSCRIPTIONS[subscription_id] = meta

    if db is not None:
        try:
            from AINDY.db.models.webhook_subscription import WebhookSubscription as WS
            db.add(WS(
                id=uuid.UUID(subscription_id),
                event_type=event_type,
                callback_url=callback_url,
                secret=secret,
                created_by=str(user_id) if user_id else None,
                created_at=now,
                is_active=True,
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("platform: failed to persist subscription %s: %s", subscription_id, exc)

    logger.info(
        "webhook subscription created: id=%s event_type=%s url=%s",
        subscription_id, event_type, callback_url,
    )
    return _public_meta(meta)


def _load_subscription(
    subscription_id: str,
    event_type: str,
    callback_url: str,
    *,
    secret: str | None,
    user_id: str | None,
    created_at: str,
) -> None:
    """
    Internal: restore a persisted subscription into _SUBSCRIPTIONS without
    hitting the DB again.  Called exclusively by the startup platform loader.

    Uses the stored subscription_id so existing client references remain valid.
    Idempotent â€” skips silently if the id is already loaded.
    """
    with _webhook_lock:
        if subscription_id in _SUBSCRIPTIONS:
            return
        _SUBSCRIPTIONS[subscription_id] = {
            "id": subscription_id,
            "event_type": event_type,
            "callback_url": callback_url,
            "signed": secret is not None,
            "_secret": secret,
            "created_at": created_at,
            "created_by": user_id,
            "delivery_attempts": 0,
            "delivery_successes": 0,
            "delivery_failures": 0,
            "last_delivered_at": None,
            "last_status": None,
        }


def unsubscribe_webhook(subscription_id: str, *, db: Session | None = None) -> bool:
    """
    Remove a subscription from memory and optionally soft-delete from DB.

    Returns True if removed, False if not found.
    """
    with _webhook_lock:
        if subscription_id not in _SUBSCRIPTIONS:
            return False
        _SUBSCRIPTIONS.pop(subscription_id)

    if db is not None:
        try:
            from AINDY.db.models.webhook_subscription import WebhookSubscription as WS
            row = db.query(WS).filter(WS.id == uuid.UUID(subscription_id)).first()
            if row:
                row.is_active = False
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("platform: failed to soft-delete subscription %s: %s", subscription_id, exc)

    logger.info("webhook subscription deleted: id=%s", subscription_id)
    return True


def list_webhooks(user_id: str | None = None) -> list[dict[str, Any]]:
    """Return all subscriptions, optionally filtered by creator user_id."""
    subs = list(_SUBSCRIPTIONS.values())
    if user_id is not None:
        subs = [s for s in subs if s.get("created_by") == user_id]
    return [_public_meta(s) for s in subs]


def get_webhook(subscription_id: str) -> dict[str, Any] | None:
    """Return public metadata for one subscription, or None if not found."""
    sub = _SUBSCRIPTIONS.get(subscription_id)
    return _public_meta(sub) if sub else None


def _public_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Strip the internal _secret field before returning to callers."""
    return {k: v for k, v in meta.items() if k != "_secret"}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _build_request_body(
    *,
    event_type: str,
    event_id: str,
    payload: dict[str, Any],
    user_id: str | None,
    trace_id: str | None,
    source: str | None,
    subscription_id: str,
) -> bytes:
    body = {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "trace_id": trace_id,
        "source": source,
        "payload": payload,
        "aindy_subscription_id": subscription_id,
    }
    return json.dumps(body, default=str).encode("utf-8")


def _send_with_retry(
    *,
    subscription_id: str,
    url: str,
    body_bytes: bytes,
    secret: str | None,
    max_attempts: int,
    timeout: int,
) -> bool:
    """
    Attempt delivery up to max_attempts times with exponential back-off.

    Returns True if any attempt succeeds (HTTP 2xx), False otherwise.
    Never raises â€” all exceptions are caught and logged.
    """
    import urllib.error
    import urllib.request

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "AINDY-EventDispatcher/1.0",
    }
    if secret:
        sig = hmac.new(
            secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()
        headers["X-AINDY-Signature"] = f"sha256={sig}"

    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(
                url, data=body_bytes, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
            if 200 <= status_code < 300:
                logger.debug(
                    "webhook delivered: sub=%s attempt=%d status=%d",
                    subscription_id, attempt, status_code,
                )
                return True
            logger.warning(
                "webhook non-2xx: sub=%s attempt=%d status=%d",
                subscription_id, attempt, status_code,
            )
        except Exception as exc:
            logger.warning(
                "webhook error: sub=%s attempt=%d error=%s",
                subscription_id, attempt, exc,
            )

        if attempt < max_attempts:
            backoff = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            time.sleep(backoff)

    return False


def _deliver_one(
    sub: dict[str, Any],
    body_bytes: bytes,
) -> None:
    """Deliver to one subscription and update its stats in-place."""
    sub_id = sub["id"]
    success = _send_with_retry(
        subscription_id=sub_id,
        url=sub["callback_url"],
        body_bytes=body_bytes,
        secret=sub.get("_secret"),
        max_attempts=_MAX_ATTEMPTS,
        timeout=_ATTEMPT_TIMEOUT,
    )
    with _webhook_lock:
        live = _SUBSCRIPTIONS.get(sub_id)
        if live is None:
            return   # subscription was deleted while we were delivering
        live["delivery_attempts"] = (live.get("delivery_attempts") or 0) + 1
        if success:
            live["delivery_successes"] = (live.get("delivery_successes") or 0) + 1
            live["last_status"] = "success"
        else:
            live["delivery_failures"] = (live.get("delivery_failures") or 0) + 1
            live["last_status"] = "failed"
        live["last_delivered_at"] = datetime.now(timezone.utc).isoformat()


def dispatch_webhooks(
    *,
    event_type: str,
    event_id: str,
    payload: dict[str, Any],
    user_id: str | None,
    trace_id: str | None,
    source: str | None,
) -> int:
    """
    Dispatch event to all matching subscriptions synchronously.

    Returns the count of matching subscriptions dispatched to.
    Each delivery runs its own retry loop; failures are isolated.
    Intended to be called from a background thread â€” never call from the
    hot request path directly.
    """
    matches = [
        sub for sub in list(_SUBSCRIPTIONS.values())
        if _matches(sub["event_type"], event_type)
    ]
    if not matches:
        return 0

    for sub in matches:
        body_bytes = _build_request_body(
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            user_id=user_id,
            trace_id=trace_id,
            source=source,
            subscription_id=sub["id"],
        )
        try:
            _deliver_one(sub, body_bytes)
        except Exception as exc:
            logger.warning(
                "webhook dispatch error: sub=%s event=%s error=%s",
                sub["id"], event_type, exc,
            )

    return len(matches)


def dispatch_webhooks_async(
    *,
    event_type: str,
    event_id: str,
    payload: dict[str, Any],
    user_id: str | None,
    trace_id: str | None,
    source: str | None,
) -> None:
    """
    Fire-and-forget: submit webhook dispatches to the background thread pool.

    Returns immediately â€” caller is never blocked by delivery.
    """
    if not _SUBSCRIPTIONS:
        return   # fast path: no subscriptions registered

    try:
        _executor.submit(
            dispatch_webhooks,
            event_type=event_type,
            event_id=event_id,
            payload=payload or {},
            user_id=user_id,
            trace_id=trace_id,
            source=source,
        )
    except RuntimeError:
        # Executor was shut down (e.g. during test teardown) â€” log and skip
        logger.debug("webhook executor shut down; skipping dispatch for %s", event_type)
    except Exception as exc:
        logger.warning("webhook async submit failed: %s", exc)

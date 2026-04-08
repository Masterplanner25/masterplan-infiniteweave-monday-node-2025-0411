"""
WaitCondition — structured descriptor for why an ExecutionUnit is suspended.

Used by:
- ExecutionUnit.wait_condition  (JSONB column — persisted state)
- SchedulerEngine._waiting      (in-memory scheduling entry)
- ExecutionWaitSignal           (raise-based WAIT request from handlers)
- register_wait()               (canonical WAIT registration API)

Types
-----
"event"
    EU is waiting for a named system event to fire.
    ``event_name`` must be set.  When ``notify_event(event_name)`` is called,
    all EUs waiting for that event are re-enqueued.

"time"
    EU is waiting until a UTC datetime passes.
    ``trigger_at`` must be set.  SchedulerEngine.tick_time_waits() scans for
    expired time-based waits on every schedule() heartbeat cycle and promotes
    them to the ready queue.

"external"
    EU is waiting for a signal originating outside the system boundary
    (webhook, third-party callback, operator action, etc.).
    Treated identically to "event" by the scheduler — something external calls
    ``notify_event(event_name)`` to wake it.  Labelled separately so audit
    queries can distinguish internal event routing from external integrations.

Serialisation
-------------
``to_dict()`` / ``from_dict()`` round-trip cleanly through JSONB.
``trigger_at`` is stored as an ISO-8601 string; parsing is UTC-aware.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Valid condition types — stored verbatim in JSONB.
WAIT_TYPE_EVENT = "event"
WAIT_TYPE_TIME = "time"
WAIT_TYPE_EXTERNAL = "external"

_VALID_TYPES = {WAIT_TYPE_EVENT, WAIT_TYPE_TIME, WAIT_TYPE_EXTERNAL}


@dataclass
class WaitCondition:
    """
    Describes what a suspended ExecutionUnit is waiting for.

    Attributes
    ----------
    type:
        One of ``"event"``, ``"time"``, or ``"external"``.
    trigger_at:
        UTC datetime at which the EU should be resumed.  Required when
        ``type == "time"``, ignored otherwise.
    event_name:
        Event type string the EU is waiting for.  Required when
        ``type == "event"`` or ``"external"``.  Used as the key for
        ``SchedulerEngine.notify_event(event_name)``.
    correlation_id:
        Optional propagated correlation/trace ID.  Stored for observability;
        not used for scheduling decisions.
    """

    type: str
    trigger_at: Optional[datetime] = None
    event_name: Optional[str] = None
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.type not in _VALID_TYPES:
            raise ValueError(
                f"WaitCondition.type must be one of {sorted(_VALID_TYPES)!r}, got {self.type!r}"
            )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSONB storage."""
        return {
            "type": self.type,
            "trigger_at": self.trigger_at.isoformat() if self.trigger_at else None,
            "event_name": self.event_name,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WaitCondition":
        """Deserialise from a JSONB-stored dict.  Returns None-safe."""
        if not data:
            return cls(type=WAIT_TYPE_EVENT)
        trigger_at = _parse_utc_datetime(data.get("trigger_at"))
        return cls(
            type=str(data.get("type") or WAIT_TYPE_EVENT),
            trigger_at=trigger_at,
            event_name=data.get("event_name") or None,
            correlation_id=data.get("correlation_id") or None,
        )

    # ── Factory helpers ───────────────────────────────────────────────────────

    @classmethod
    def for_event(
        cls,
        event_name: str,
        *,
        correlation_id: str | None = None,
    ) -> "WaitCondition":
        """EU waits for an internal system event named ``event_name``."""
        return cls(
            type=WAIT_TYPE_EVENT,
            event_name=event_name,
            correlation_id=correlation_id,
        )

    @classmethod
    def for_time(
        cls,
        trigger_at: datetime,
        *,
        correlation_id: str | None = None,
    ) -> "WaitCondition":
        """EU waits until ``trigger_at`` (UTC) passes."""
        if trigger_at.tzinfo is None:
            trigger_at = trigger_at.replace(tzinfo=timezone.utc)
        return cls(
            type=WAIT_TYPE_TIME,
            trigger_at=trigger_at,
            correlation_id=correlation_id,
        )

    @classmethod
    def for_external(
        cls,
        event_name: str,
        *,
        correlation_id: str | None = None,
    ) -> "WaitCondition":
        """EU waits for an external trigger identified by ``event_name``."""
        return cls(
            type=WAIT_TYPE_EXTERNAL,
            event_name=event_name,
            correlation_id=correlation_id,
        )

    # ── Convenience ───────────────────────────────────────────────────────────

    @property
    def is_time_based(self) -> bool:
        return self.type == WAIT_TYPE_TIME

    @property
    def is_event_based(self) -> bool:
        return self.type in {WAIT_TYPE_EVENT, WAIT_TYPE_EXTERNAL}

    @property
    def resume_event(self) -> str | None:
        """The event name to pass to ``notify_event()`` for this condition."""
        return self.event_name if self.is_event_based else None


# ── Private helpers ───────────────────────────────────────────────────────────


def _parse_utc_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None

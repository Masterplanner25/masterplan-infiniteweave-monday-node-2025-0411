from datetime import datetime, timezone


VALID_SIGNAL_TYPES = frozenset(
    [
        "session_started",
        "session_ended",
        "distraction_detected",
        "focus_achieved",
        "context_switch",
        "heartbeat",
    ]
)

VALID_ACTIVITY_TYPES = frozenset(
    ["work", "communication", "distraction", "idle", "unknown"]
)


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 UTC timestamp. Raises ValueError on failure."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:
        raise ValueError(f"Invalid timestamp: {ts_str!r}") from exc


_VALID_SIGNAL_TYPES = VALID_SIGNAL_TYPES
_VALID_ACTIVITY_TYPES = VALID_ACTIVITY_TYPES
_parse_timestamp = parse_timestamp

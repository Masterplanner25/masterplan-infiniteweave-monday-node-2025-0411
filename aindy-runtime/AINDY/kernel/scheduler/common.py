from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"
PRIORITY_ORDER = (PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW)
MAX_PER_SCHEDULE_CYCLE = 10


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


_MAX_PRE_REHYDRATION_BUFFER = _int_env(
    "AINDY_SCHEDULER_PRE_REHYDRATION_BUFFER",
    1000,
)


def _get_session_factory():
    from AINDY.db.database import SessionLocal

    return SessionLocal


def _get_instance_id() -> str:
    return os.getenv("HOSTNAME", "local")


def _emit_dispatch_failure(item: "ScheduledItem", exc: Exception) -> None:
    try:
        logger.critical(
            "[Scheduler] DISPATCH_FAILURE run_id=%s eu=%s tenant=%s type=%s retries=%d exc=%r",
            item.run_id,
            item.execution_unit_id,
            item.tenant_id,
            item.eu_type,
            item.retry_count,
            str(exc),
        )
    except Exception:
        pass


@dataclass
class _ResumedEUStub:
    id: str
    type: str
    priority: str
    extra: dict = field(default_factory=dict)


@dataclass
class ScheduledItem:
    execution_unit_id: str
    tenant_id: str
    priority: str
    run_callback: Callable[[], None]
    run_id: Optional[str] = None
    eu_type: str = "flow"
    enqueued_at_seq: int = field(default=0, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=2, compare=False)

    def __post_init__(self) -> None:
        if self.priority not in PRIORITY_ORDER:
            raise ValueError(
                f"Invalid priority {self.priority!r}; must be one of {PRIORITY_ORDER}"
            )
        if self.max_retries == 2:
            self.max_retries = _int_env("AINDY_SCHEDULER_MAX_DISPATCH_RETRIES", 2)

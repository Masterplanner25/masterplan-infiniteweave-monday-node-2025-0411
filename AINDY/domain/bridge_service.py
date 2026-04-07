from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_bridge_user_event(
    db: Session,
    *,
    user: str,
    origin: str,
    raw_timestamp: str | None,
    occurred_at: datetime,
) -> None:
    """Persist a bridge user event. Non-fatal: logs a warning on failure."""
    from db.models.bridge_user_event import BridgeUserEvent

    try:
        db.add(
            BridgeUserEvent(
                user_name=user,
                origin=origin,
                raw_timestamp=raw_timestamp,
                occurred_at=occurred_at,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to persist bridge user event: %s", exc)

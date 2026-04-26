from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


def get_user_scores(db: Session, user_ids: list[str | UUID]) -> dict[str, float]:
    """
    Return a mapping of user_id (str) → master_score for the given user_ids.

    Accepts mixed str / UUID inputs and normalises them before querying.
    Returns an empty dict when user_ids is empty.
    """
    from apps.analytics.public import get_user_scores as get_analytics_user_scores

    if not user_ids:
        return {}

    rows = get_analytics_user_scores(db=db, user_ids=[str(uid) for uid in user_ids])
    return {user_id: float(row.get("master_score") or 0.0) for user_id, row in rows.items()}

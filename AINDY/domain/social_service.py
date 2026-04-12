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
    from AINDY.db.models.user_score import UserScore

    if not user_ids:
        return {}

    uuid_ids = [UUID(str(uid)) for uid in user_ids]
    rows = db.query(UserScore).filter(UserScore.user_id.in_(uuid_ids)).all()
    return {str(row.user_id): row.master_score for row in rows}

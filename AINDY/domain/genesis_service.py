from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_owned_session(db: Session, session_id: int, user_id: str) -> Any | None:
    """Return the GenesisSessionDB for the given session_id if it belongs to user_id."""
    from AINDY.db.models import GenesisSessionDB

    return (
        db.query(GenesisSessionDB)
        .filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == uuid.UUID(str(user_id)),
        )
        .first()
    )


def restore_synthesis_ready(db: Session, session: Any, *, existing_ready: bool) -> None:
    """
    After a genesis_message flow completes, re-check synthesis_ready.

    If it was True before the flow ran but the model was refreshed to False,
    restore it to True and commit.  This guards against a race where the flow
    engine temporarily clears the flag.
    """
    db.refresh(session)
    if existing_ready and not session.synthesis_ready:
        session.synthesis_ready = True
        db.commit()


def activate_masterplan_genesis(db: Session, *, plan_id: int, user_id: str) -> dict[str, Any]:
    """
    Activate a masterplan from the Genesis flow.

    - Deactivates all other plans for the user.
    - Sets plan.is_active = True and plan.status = "active".
    - Saves a memory node recording the activation decision.

    Returns the result dict consumed by the route handler.
    Raises HTTPException on not-found.
    """
    from AINDY.db.models import MasterPlan

    uid = uuid.UUID(str(user_id))
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == uid)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "plan_not_found", "message": "Masterplan not found"},
        )

    if not getattr(plan, "is_active", False):
        (
            db.query(MasterPlan)
            .filter(MasterPlan.user_id == uid)
            .update({"is_active": False})
        )
        plan.is_active = True
        plan.status = "active"
        db.commit()

    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        MemoryNodeDAO(db).save(
            content=f"Masterplan activated: {getattr(plan, 'version_label', plan_id)}",
            source="genesis_activate",
            tags=["genesis", "masterplan", "activate"],
            user_id=user_id,
            node_type="decision",
            extra={"plan_id": getattr(plan, "id", plan_id)},
        )
    except Exception as exc:
        logger.warning("Genesis activate memory capture failed: %s", exc)

    return {
        "plan_id": getattr(plan, "id", plan_id),
        "status": getattr(plan, "status", "active"),
        "is_active": getattr(plan, "is_active", True),
    }

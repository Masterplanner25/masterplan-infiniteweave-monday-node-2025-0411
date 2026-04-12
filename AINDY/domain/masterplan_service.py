from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from AINDY.analytics.posture import posture_description
from AINDY.db.models import MasterPlan
from AINDY.domain.masterplan_factory import create_masterplan_from_genesis


# ── list_masterplans ──────────────────────────────────────────────────────────

def list_masterplans(db: Session, *, user_id: str) -> dict[str, Any]:
    """Return all masterplans for a user, newest first."""
    plans = (
        db.query(MasterPlan)
        .filter(MasterPlan.user_id == user_id)
        .order_by(MasterPlan.id.desc())
        .all()
    )
    return {
        "plans": [
            {
                "id": plan.id,
                "status": plan.status,
                "posture": plan.posture,
                "is_active": plan.is_active,
                "locked_at": plan.locked_at.isoformat() if plan.locked_at else None,
                "created_at": plan.created_at.isoformat() if plan.created_at else None,
            }
            for plan in plans
        ]
    }


# ── lock_from_genesis ─────────────────────────────────────────────────────────

def lock_from_genesis(
    db: Session,
    *,
    user_id: str,
    session_id: int | str | None,
    draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create and lock a MasterPlan from a Genesis session.

    Raises HTTPException on validation failures so the error contract
    matches what callers expect from route-level handlers.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        plan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft or {},
            db=db,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=422, detail=message) from exc
        if "already locked" in message.lower():
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=500, detail=message) from exc

    return {
        "plan_id": plan.id,
        "status": plan.status,
        "posture": plan.posture,
        "posture_description": posture_description(plan.posture),
    }


# ── set_masterplan_anchor ─────────────────────────────────────────────────────

def set_masterplan_anchor(
    db: Session,
    *,
    user_id: str,
    plan_id: int,
    anchor_date: str | None = None,
    goal_value: float | None = None,
    goal_unit: str | None = None,
    goal_description: str | None = None,
) -> dict[str, Any]:
    """
    Update the anchor / goal fields on a MasterPlan.

    Returns the updated field set.  Raises HTTPException on not-found or
    invalid anchor_date format.
    """
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Masterplan not found"},
        )

    if anchor_date is not None:
        try:
            plan.anchor_date = datetime.fromisoformat(anchor_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_anchor_date", "message": "anchor_date must be ISO format"},
            ) from exc

    if goal_value is not None:
        plan.goal_value = goal_value
    if goal_unit is not None:
        plan.goal_unit = goal_unit
    if goal_description is not None:
        plan.goal_description = goal_description

    db.commit()
    db.refresh(plan)

    return {
        "plan_id": plan.id,
        "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
        "goal_value": plan.goal_value,
        "goal_unit": plan.goal_unit,
        "goal_description": plan.goal_description,
    }


# ── get_masterplan_projection ─────────────────────────────────────────────────

def get_masterplan_projection(
    db: Session,
    *,
    user_id: str,
    plan_id: int,
) -> dict[str, Any]:
    """
    Verify the plan belongs to the user then delegate ETA calculation
    to analytics.eta_service.
    """
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Masterplan not found"},
        )

    try:
        from AINDY.analytics import eta_service

        return eta_service.calculate_eta(db=db, masterplan_id=plan_id, user_id=user_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "eta_calculation_failed", "message": str(exc)},
        ) from exc


# ── assert_masterplan_owned ───────────────────────────────────────────────────

def assert_masterplan_owned(db: Session, masterplan_id: int, user_id: str) -> Any:
    """
    Verify that masterplan_id exists and belongs to user_id.

    Returns the MasterPlan instance on success.
    Raises HTTPException 404 on not-found or ownership mismatch.
    """
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == masterplan_id, MasterPlan.user_id == user_id)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "MasterPlan not found"},
        )
    return plan

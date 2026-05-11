"""
eta_service.py — ETA projection for MasterPlans.

Calculates velocity (tasks/day over a 14-day rolling window) and projects
completion date against the user-declared anchor_date.

Public API:
    calculate_eta(db, masterplan_id, user_id) -> dict
    recalculate_all_etas(db)                  -> int  (plans updated)
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from sqlalchemy.orm import Session

from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher
from AINDY.platform_layer.user_ids import require_user_id

from apps.masterplan.models import MasterPlan

logger = logging.getLogger(__name__)

VELOCITY_WINDOW_DAYS = 14
CONFIDENCE_HIGH_MIN_TASKS = 5
CONFIDENCE_MEDIUM_MIN_TASKS = 2


def _dispatch_task_read(payload: dict, *, db: Session, user_id: str, capability: str) -> dict:
    syscall_name = str(payload.pop("_syscall"))
    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=[capability],
        trace_id="",
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(syscall_name, payload, ctx)
    if result.get("status") != "success":
        raise RuntimeError(result.get("error") or "task read syscall failed")
    return result.get("data") or {}


def _count_tasks(db: Session, *, user_id: str, status: str | None = None) -> int:
    payload: dict = {"_syscall": "sys.v1.task.count"}
    if status is not None:
        payload["status"] = status
    return int(
        _dispatch_task_read(payload, db=db, user_id=user_id, capability="task.read").get("count")
        or 0
    )


def _count_tasks_completed_since(db: Session, *, user_id: str, since: datetime) -> int:
    return int(
        _dispatch_task_read(
            {"_syscall": "sys.v1.task.count_completed_since", "since": since.isoformat()},
            db=db,
            user_id=user_id,
            capability="task.read",
        ).get("count")
        or 0
    )


def _compute_velocity(db: Session, user_id: str) -> float:
    """Return tasks/day completed in the last VELOCITY_WINDOW_DAYS days."""
    owner_user_id = require_user_id(user_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=VELOCITY_WINDOW_DAYS)
    count = _count_tasks_completed_since(
        db,
        user_id=owner_user_id,
        since=cutoff,
    )
    return count / VELOCITY_WINDOW_DAYS


def _confidence_label(velocity: float, completed_in_window: int) -> str:
    if velocity == 0 or completed_in_window < CONFIDENCE_MEDIUM_MIN_TASKS:
        return "insufficient_data"
    if completed_in_window >= CONFIDENCE_HIGH_MIN_TASKS:
        return "high"
    if completed_in_window >= CONFIDENCE_MEDIUM_MIN_TASKS:
        return "medium"
    return "low"


def _total_tasks_for_user(db: Session, user_id: str) -> int:
    return _count_tasks(db, user_id=str(require_user_id(user_id)))


def _completed_tasks_for_user(db: Session, user_id: str) -> int:
    return _count_tasks(db, user_id=str(require_user_id(user_id)), status="completed")


def calculate_eta(db: Session, masterplan_id: int, user_id: str) -> dict:
    """
    Compute ETA projection for a single MasterPlan and persist results.

    Returns:
        dict with keys: velocity, projected_completion_date, days_ahead_behind,
        eta_confidence, anchor_date, total_tasks, completed_tasks, remaining_tasks
    """
    owner_user_id = require_user_id(user_id)
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == masterplan_id, MasterPlan.user_id == owner_user_id)
        .first()
    )
    if not plan:
        raise ValueError(f"MasterPlan {masterplan_id} not found for user {user_id}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=VELOCITY_WINDOW_DAYS)
    tasks_in_window = _count_tasks_completed_since(
        db,
        user_id=owner_user_id,
        since=cutoff,
    )
    velocity = tasks_in_window / VELOCITY_WINDOW_DAYS

    total = _total_tasks_for_user(db, owner_user_id)
    completed = _completed_tasks_for_user(db, owner_user_id)
    remaining = max(total - completed, 0)

    projected: Optional[date] = None
    days_ahead_behind: Optional[int] = None

    if velocity > 0 and remaining >= 0:
        days_needed = remaining / velocity
        projected = (datetime.now(timezone.utc) + timedelta(days=days_needed)).date()

        if plan.anchor_date:
            anchor = plan.anchor_date.date() if hasattr(plan.anchor_date, "date") else plan.anchor_date
            days_ahead_behind = (anchor - projected).days

    confidence = _confidence_label(velocity, tasks_in_window)

    # Persist to plan
    plan.current_velocity = velocity
    plan.projected_completion_date = projected
    plan.days_ahead_behind = days_ahead_behind
    plan.eta_last_calculated = datetime.now(timezone.utc)
    plan.eta_confidence = confidence
    db.commit()

    return {
        "masterplan_id": masterplan_id,
        "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
        "velocity": velocity,
        "projected_completion_date": projected.isoformat() if projected else None,
        "days_ahead_behind": days_ahead_behind,
        "eta_confidence": confidence,
        "total_tasks": total,
        "completed_tasks": completed,
        "remaining_tasks": remaining,
        "eta_last_calculated": plan.eta_last_calculated.isoformat(),
    }


def recalculate_all_etas(db: Session) -> int:
    """
    Recalculate ETA for every active MasterPlan that has an anchor_date set.
    Called by the daily APScheduler job.
    Returns the count of plans updated.
    """
    plans = (
        db.query(MasterPlan)
        .filter(MasterPlan.anchor_date.isnot(None))
        .all()
    )
    updated = 0
    for plan in plans:
        try:
            calculate_eta(db=db, masterplan_id=plan.id, user_id=plan.user_id)
            updated += 1
        except Exception as exc:
            logger.warning("ETA recalc failed for plan %s: %s", plan.id, exc)
    return updated


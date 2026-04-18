from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session


def list_calculation_results(db: Session, *, user_id: str) -> list[Any]:
    """Return all CalculationResult rows for a user."""
    from apps.analytics.models import CalculationResult

    return (
        db.query(CalculationResult)
        .filter(CalculationResult.user_id == uuid.UUID(str(user_id)))
        .all()
    )


def list_masterplans_compute(db: Session, *, user_id: str) -> list[Any]:
    """Return all MasterPlan rows for a user (compute/legacy endpoint)."""
    from apps.masterplan.models import MasterPlan

    return (
        db.query(MasterPlan)
        .filter(MasterPlan.user_id == uuid.UUID(str(user_id)))
        .all()
    )


def create_masterplan_compute(db: Session, *, data: dict[str, Any], user_id: str) -> Any:
    """Create and persist a new MasterPlan from raw field data."""
    from apps.masterplan.models import MasterPlan

    plan = MasterPlan(**data)
    plan.user_id = uuid.UUID(str(user_id))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

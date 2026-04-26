"""Public contract for the automation app."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy.orm import Session

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError
from apps.automation.models import (
    AutomationLog,
    BridgeUserEvent,
    LearningRecordDB,
    LearningThresholdDB,
    LoopAdjustment,
    UserFeedback,
)
from apps.automation.services.automation_execution_service import (
    execute_automation_action as _execute_automation_action,
)
from apps.automation.services.job_log_sync_service import (
    sync_job_log_to_automation_log as _sync_job_log_to_automation_log,
)

PUBLIC_API_VERSION = "1.0"
_CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}


class AutomationActionResult(TypedDict, total=False):
    automation_type: str
    status: str
    post_id: str
    content: str
    requested_post_id: str | None
    action: str
    contact: str | None
    details: str | None
    task_id: int | None
    subject: str
    recipient: str
    sender: str
    transport: str
    host: str
    port: int
    endpoint: str
    provider_response: dict[str, Any]
    subscription_id: str
    customer_id: str
    invoice_id: str
    prompt: str
    generated_content: str


def _serialize_scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _row_to_dict(row) -> dict[str, Any]:
    """Convert an ORM row to a plain dict using its __dict__."""
    return {
        key: _serialize_scalar(value)
        for key, value in row.__dict__.items()
        if not key.startswith("_")
    }


def _get_circuit_breaker(function_name: str) -> CircuitBreaker:
    key = f"automation.public.{function_name}"
    breaker = _CIRCUIT_BREAKERS.get(key)
    if breaker is None:
        breaker = CircuitBreaker(name=key)
        _CIRCUIT_BREAKERS[key] = breaker
    return breaker


def _call_with_circuit_breaker(function_name: str, fallback: Any, func) -> Any:
    breaker = _get_circuit_breaker(function_name)
    try:
        return breaker.call(func)
    except CircuitOpenError:
        import logging

        logging.getLogger(__name__).warning(
            "automation circuit open, returning fallback for %s",
            function_name,
        )
        return fallback


def execute_automation_action(
    payload: dict[str, Any],
    db: Session,
) -> AutomationActionResult:
    """Execute a single automation action from an app-provided payload."""
    return _call_with_circuit_breaker(
        "execute_automation_action",
        {},
        lambda: _execute_automation_action(payload, db),
    )


def sync_job_log_to_automation_log(db: Session, job_log_row: Any) -> None:
    """Mirror an execution job log row into the automation log table."""
    _call_with_circuit_breaker(
        "sync_job_log_to_automation_log",
        None,
        lambda: _sync_job_log_to_automation_log(db, job_log_row),
    )


def get_loop_adjustments(
    user_id: str | UUID,
    db: Session,
    *,
    limit: int = 10,
    with_prediction_accuracy: bool = False,
    unevaluated_only: bool = False,
    decision_type: str | None = None,
    with_actual_score: bool = False,
    with_expected_score: bool = False,
    order_by: str = "applied_desc",
    for_update: bool = False,
) -> list[dict[str, Any]]:
    """Return LoopAdjustment records as plain dicts."""
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.automation.models import LoopAdjustment

    uid = parse_user_id(user_id)
    if uid is None:
        return []

    query = db.query(LoopAdjustment).filter(LoopAdjustment.user_id == uid)
    if with_prediction_accuracy:
        query = query.filter(LoopAdjustment.prediction_accuracy.isnot(None))
    if unevaluated_only:
        query = query.filter(LoopAdjustment.evaluated_at.is_(None))
    if decision_type:
        query = query.filter(LoopAdjustment.decision_type == decision_type)
    if with_actual_score:
        query = query.filter(LoopAdjustment.actual_score.isnot(None))
    if with_expected_score:
        query = query.filter(LoopAdjustment.expected_score.isnot(None))
    if for_update:
        query = query.with_for_update()

    if order_by == "evaluated_desc":
        query = query.order_by(LoopAdjustment.evaluated_at.desc(), LoopAdjustment.created_at.desc())
    elif order_by == "created_desc":
        query = query.order_by(LoopAdjustment.created_at.desc())
    else:
        query = query.order_by(LoopAdjustment.applied_at.desc(), LoopAdjustment.created_at.desc())

    return [_row_to_dict(row) for row in query.limit(limit).all()]


def get_user_feedback(
    user_id: str | UUID,
    db: Session,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return UserFeedback records as plain dicts."""
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.automation.models import UserFeedback

    uid = parse_user_id(user_id)
    if uid is None:
        return []

    rows = (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == uid)
        .order_by(UserFeedback.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_row_to_dict(row) for row in rows]


def create_loop_adjustment(db: Session, **kwargs) -> dict[str, Any]:
    """Create a LoopAdjustment record. Returns the created record as a dict."""
    from apps.automation.models import LoopAdjustment

    record = LoopAdjustment(**kwargs)
    db.add(record)
    db.flush()
    return _row_to_dict(record)


def update_loop_adjustment(
    adjustment_id: str | UUID,
    db: Session,
    **kwargs,
) -> dict[str, Any] | None:
    """Update one LoopAdjustment record and return it as a dict."""
    from apps.automation.models import LoopAdjustment

    row = db.query(LoopAdjustment).filter(LoopAdjustment.id == adjustment_id).first()
    if row is None:
        return None
    for key, value in kwargs.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return _row_to_dict(row)


__all__ = [
    "execute_automation_action",
    "get_loop_adjustments",
    "get_user_feedback",
    "create_loop_adjustment",
]

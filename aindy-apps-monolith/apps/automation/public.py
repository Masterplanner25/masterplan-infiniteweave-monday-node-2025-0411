"""
Public contract for the automation app.
Consumers: analytics, bridge, freelance, masterplan, rippletrace, tasks
"""

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


def create_bridge_user_event(
    db: Session,
    *,
    user: str,
    origin: str,
    raw_timestamp: str | None,
    occurred_at: datetime,
) -> dict[str, Any]:
    """Create one bridge-originated user event row."""
    from apps.automation.services.public_surface_service import (
        create_bridge_user_event as _create_bridge_user_event,
        row_to_dict,
    )

    return row_to_dict(
        _create_bridge_user_event(
            db,
            user=user,
            origin=origin,
            raw_timestamp=raw_timestamp,
            occurred_at=occurred_at,
        )
    )


def list_automation_logs(
    db: Session,
    *,
    user_id: str | UUID,
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Return recent automation logs as plain dicts."""
    from apps.automation.services.public_surface_service import (
        list_automation_logs as _list_automation_logs,
        row_to_dict,
    )

    return [row_to_dict(row) for row in _list_automation_logs(db, user_id=user_id, limit=limit)]


def list_watcher_signals(
    db: Session,
    *,
    session_id: str | None = None,
    user_id: str | UUID | None = None,
    signal_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return watcher signals as plain dicts."""
    from apps.automation.services.public_surface_service import (
        list_watcher_signals as _list_watcher_signals,
        row_to_dict,
    )

    rows = _list_watcher_signals(
        db,
        session_id=session_id,
        user_id=user_id,
        signal_type=signal_type,
        limit=limit,
        offset=offset,
    )
    data = [row_to_dict(row) for row in rows]
    for row in data:
        if "signal_metadata" in row and "metadata" not in row:
            row["metadata"] = row["signal_metadata"]
    return data


def persist_watcher_signals(
    db: Session,
    *,
    signals: list[dict[str, Any]],
    user_id: str | UUID,
) -> dict[str, Any]:
    """Persist watcher signals and return ingestion counts."""
    from apps.automation.services.public_surface_service import (
        persist_watcher_signals as _persist_watcher_signals,
    )

    return dict(_persist_watcher_signals(db, signals=signals, user_id=user_id) or {})


def ensure_learning_thresholds(
    db: Session,
    *,
    velocity_trend: float,
    narrative_trend: float,
    early_velocity_rate: float,
    early_narrative_ceiling: float,
) -> dict[str, Any]:
    """Return the current learning thresholds, creating defaults when absent."""
    from apps.automation.services.public_surface_service import (
        create_learning_threshold_row,
        get_learning_threshold_row,
        row_to_dict,
    )

    row = get_learning_threshold_row(db)
    if row is None:
        row = create_learning_threshold_row(
            db,
            velocity_trend=velocity_trend,
            narrative_trend=narrative_trend,
            early_velocity_rate=early_velocity_rate,
            early_narrative_ceiling=early_narrative_ceiling,
        )
    return row_to_dict(row)


def update_learning_thresholds(
    db: Session,
    *,
    threshold_id: str,
    **kwargs,
) -> dict[str, Any] | None:
    """Update one learning-threshold row."""
    from apps.automation.services.public_surface_service import (
        row_to_dict,
        update_learning_threshold_row,
    )

    row = update_learning_threshold_row(db, threshold_id=threshold_id, **kwargs)
    return row_to_dict(row) if row is not None else None


def create_learning_record(db: Session, **kwargs) -> dict[str, Any]:
    """Create one learning record row and return it as a plain dict."""
    from apps.automation.services.public_surface_service import (
        create_learning_record_row,
        row_to_dict,
    )

    return row_to_dict(create_learning_record_row(db, **kwargs))


def get_latest_learning_record(
    db: Session,
    *,
    drop_point_id: str,
    pending_only: bool = False,
) -> dict[str, Any] | None:
    """Return the newest learning record for one drop point."""
    from apps.automation.services.public_surface_service import (
        get_latest_learning_record_row,
        row_to_dict,
    )

    row = get_latest_learning_record_row(
        db,
        drop_point_id=drop_point_id,
        pending_only=pending_only,
    )
    return row_to_dict(row) if row is not None else None


def list_learning_records(
    db: Session,
    *,
    limit: int | None = None,
    evaluated_only: bool = False,
) -> list[dict[str, Any]]:
    """List learning records as plain dicts."""
    from apps.automation.services.public_surface_service import (
        list_learning_record_rows,
        row_to_dict,
    )

    rows = list_learning_record_rows(db, limit=limit, evaluated_only=evaluated_only)
    return [row_to_dict(row) for row in rows]


def list_learning_record_drop_point_ids(
    db: Session,
    *,
    actual_outcome: str | None = None,
) -> list[str]:
    """List distinct drop-point IDs from learning records."""
    from apps.automation.services.public_surface_service import (
        list_learning_record_drop_point_ids as _list_learning_record_drop_point_ids,
    )

    return list(_list_learning_record_drop_point_ids(db, actual_outcome=actual_outcome) or [])


def update_learning_record(
    db: Session,
    *,
    record_id: str,
    **kwargs,
) -> dict[str, Any] | None:
    """Update one learning record row."""
    from apps.automation.services.public_surface_service import (
        row_to_dict,
        update_learning_record_row,
    )

    row = update_learning_record_row(db, record_id=record_id, **kwargs)
    return row_to_dict(row) if row is not None else None


__all__ = [
    "execute_automation_action",
    "get_loop_adjustments",
    "get_user_feedback",
    "create_loop_adjustment",
    "update_loop_adjustment",
    "create_bridge_user_event",
    "list_automation_logs",
    "list_watcher_signals",
    "persist_watcher_signals",
    "ensure_learning_thresholds",
    "update_learning_thresholds",
    "create_learning_record",
    "get_latest_learning_record",
    "list_learning_records",
    "list_learning_record_drop_point_ids",
    "update_learning_record",
]

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy.orm import Session

from AINDY.platform_layer.user_ids import parse_user_id


def serialize_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def row_to_dict(row) -> dict[str, Any]:
    return {
        key: serialize_scalar(value)
        for key, value in row.__dict__.items()
        if not key.startswith("_")
    }


def create_bridge_user_event(
    db: Session,
    *,
    user: str,
    origin: str,
    raw_timestamp: str | None,
    occurred_at: datetime,
):
    from apps.automation.models import BridgeUserEvent

    record = BridgeUserEvent(
        user_name=user,
        origin=origin,
        raw_timestamp=raw_timestamp,
        occurred_at=occurred_at,
    )
    db.add(record)
    db.flush()
    return record


def list_automation_logs(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    limit: int = 250,
) -> list:
    from apps.automation.models import AutomationLog

    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []
    return (
        db.query(AutomationLog)
        .filter(AutomationLog.user_id == owner_user_id)
        .order_by(AutomationLog.created_at.desc())
        .limit(limit)
        .all()
    )


def list_watcher_signals(
    db: Session,
    *,
    session_id: str | None = None,
    user_id: str | uuid.UUID | None = None,
    signal_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    from apps.automation.models import WatcherSignal

    query = db.query(WatcherSignal)
    if session_id:
        query = query.filter(WatcherSignal.session_id == session_id)
    if user_id is not None:
        owner_user_id = parse_user_id(user_id)
        if owner_user_id is None:
            return []
        query = query.filter(WatcherSignal.user_id == owner_user_id)
    if signal_type:
        query = query.filter(WatcherSignal.signal_type == signal_type)
    return (
        query.order_by(WatcherSignal.signal_timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def persist_watcher_signals(
    db: Session,
    *,
    signals: list[dict[str, Any]],
    user_id: str | uuid.UUID,
) -> dict[str, Any]:
    from apps.automation.models import WatcherSignal
    from AINDY.platform_layer.watcher_contract import (
        get_valid_activity_types,
        get_valid_signal_types,
        parse_signal_timestamp,
    )

    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        raise ValueError("watcher.persist requires a valid user_id")

    persisted = 0
    session_ended_count = 0
    for idx, sig in enumerate(signals):
        signal_type = sig.get("signal_type")
        activity_type = sig.get("activity_type")
        if signal_type not in get_valid_signal_types():
            raise ValueError(f"Signal [{idx}]: unknown signal_type {signal_type!r}")
        if activity_type not in get_valid_activity_types():
            raise ValueError(f"Signal [{idx}]: unknown activity_type {activity_type!r}")

        meta = sig.get("metadata") or {}
        db.add(
            WatcherSignal(
                signal_type=signal_type,
                session_id=sig.get("session_id"),
                user_id=owner_user_id,
                app_name=sig.get("app_name"),
                window_title=sig.get("window_title") or None,
                activity_type=activity_type,
                signal_timestamp=parse_signal_timestamp(sig.get("timestamp")),
                received_at=datetime.now(timezone.utc),
                duration_seconds=meta.get("duration_seconds"),
                focus_score=meta.get("focus_score"),
                signal_metadata=meta if meta else None,
            )
        )
        if signal_type == "session_ended":
            session_ended_count += 1
        persisted += 1

    db.commit()
    return {
        "accepted": persisted,
        "session_ended_count": session_ended_count,
        "watcher_batch_user_id": str(owner_user_id),
    }


def get_learning_threshold_row(db: Session):
    from apps.automation.models import LearningThresholdDB

    return db.query(LearningThresholdDB).first()


def create_learning_threshold_row(
    db: Session,
    *,
    velocity_trend: float,
    narrative_trend: float,
    early_velocity_rate: float,
    early_narrative_ceiling: float,
    last_updated: datetime | None = None,
):
    from apps.automation.models import LearningThresholdDB

    row = LearningThresholdDB(
        id=str(uuid.uuid4()),
        velocity_trend=velocity_trend,
        narrative_trend=narrative_trend,
        early_velocity_rate=early_velocity_rate,
        early_narrative_ceiling=early_narrative_ceiling,
        last_updated=last_updated or datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_learning_threshold_row(db: Session, *, threshold_id: str, **kwargs):
    from apps.automation.models import LearningThresholdDB

    row = db.query(LearningThresholdDB).filter(LearningThresholdDB.id == threshold_id).first()
    if row is None:
        return None
    for key, value in kwargs.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_learning_record_row(db: Session, **kwargs):
    from apps.automation.models import LearningRecordDB

    row = LearningRecordDB(id=kwargs.pop("id", str(uuid.uuid4())), **kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_learning_record_row(
    db: Session,
    *,
    drop_point_id: str,
    pending_only: bool = False,
):
    from apps.automation.models import LearningRecordDB

    query = db.query(LearningRecordDB).filter(LearningRecordDB.drop_point_id == drop_point_id)
    if pending_only:
        query = query.filter(LearningRecordDB.actual_outcome.is_(None))
    return query.order_by(LearningRecordDB.predicted_at.desc()).first()


def list_learning_record_rows(
    db: Session,
    *,
    limit: int | None = None,
    evaluated_only: bool = False,
) -> list:
    from apps.automation.models import LearningRecordDB

    query = db.query(LearningRecordDB)
    if evaluated_only:
        query = query.filter(LearningRecordDB.actual_outcome.isnot(None))
    query = query.order_by(LearningRecordDB.predicted_at.desc())
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def list_learning_record_drop_point_ids(
    db: Session,
    *,
    actual_outcome: str | None = None,
) -> list[str]:
    from apps.automation.models import LearningRecordDB

    query = db.query(LearningRecordDB.drop_point_id)
    if actual_outcome is not None:
        query = query.filter(LearningRecordDB.actual_outcome == actual_outcome)
    rows = query.distinct().all()
    return [row[0] for row in rows if row and row[0]]


def update_learning_record_row(db: Session, *, record_id: str, **kwargs):
    from apps.automation.models import LearningRecordDB

    row = db.query(LearningRecordDB).filter(LearningRecordDB.id == record_id).first()
    if row is None:
        return None
    for key, value in kwargs.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

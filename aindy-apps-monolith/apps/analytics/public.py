"""
Public contract for apps/analytics.

External apps must import from this module, never from
apps.analytics.services.* directly. This file is the contract boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError
from AINDY.platform_layer.user_ids import parse_user_id
from apps.analytics.models import CalculationResult
from apps.analytics.services.calculations.calculation_services import (
    calculate_twr,
    save_calculation as _save_calculation,
)
from apps.analytics.services.orchestration.infinity_loop import (
    get_latest_adjustment,
)
from apps.analytics.services.orchestration.infinity_orchestrator import (
    execute as _run_infinity_orchestrator,
)
from apps.analytics.services.scoring.infinity_service import (
    get_user_kpi_snapshot as _get_user_kpi_snapshot,
)

PUBLIC_API_VERSION = "1.0"
_CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}


class UserScoreDict(TypedDict):
    id: str
    user_id: str
    master_score: float
    execution_speed_score: float
    decision_efficiency_score: float
    ai_productivity_boost_score: float
    focus_quality_score: float
    masterplan_progress_score: float
    score_version: str
    data_points_used: int
    confidence: str | None
    trigger_event: str | None
    lock_version: int
    calculated_at: str | None
    created_at: str | None
    updated_at: str | None


class ScoreSnapshotDict(TypedDict):
    id: str
    drop_point_id: str
    timestamp: str | None
    narrative_score: float
    velocity_score: float
    spread_score: float


class UserKpiSnapshotDict(TypedDict):
    master_score: float
    execution_speed: float
    decision_efficiency: float
    ai_productivity_boost: float
    focus_quality: float
    masterplan_progress: float
    confidence: str | None


class MemoryInfluenceDict(TypedDict):
    memory_adjustment: dict[str, Any]
    memory_summary: dict[str, Any]


class InfinityOrchestratorResult(TypedDict):
    score: dict[str, Any]
    prior_evaluation: dict[str, Any] | None
    adjustment: dict[str, Any]
    next_action: str | None
    memory_context_count: int
    memory_signal_count: int
    memory_influence: MemoryInfluenceDict


def _get_circuit_breaker(function_name: str) -> CircuitBreaker:
    key = f"analytics.public.{function_name}"
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
            "analytics circuit open, returning fallback for %s",
            function_name,
        )
        return fallback


def _score_row_to_dict(score: Any) -> UserScoreDict:
    return {
        "id": score.id,
        "user_id": str(score.user_id),
        "master_score": score.master_score,
        "execution_speed_score": score.execution_speed_score,
        "decision_efficiency_score": score.decision_efficiency_score,
        "ai_productivity_boost_score": score.ai_productivity_boost_score,
        "focus_quality_score": score.focus_quality_score,
        "masterplan_progress_score": score.masterplan_progress_score,
        "score_version": score.score_version,
        "data_points_used": score.data_points_used,
        "confidence": score.confidence,
        "trigger_event": score.trigger_event,
        "lock_version": score.lock_version,
        "calculated_at": score.calculated_at.isoformat() if score.calculated_at else None,
        "created_at": score.created_at.isoformat() if score.created_at else None,
        "updated_at": score.updated_at.isoformat() if score.updated_at else None,
    }


def _score_snapshot_to_dict(snapshot: Any) -> ScoreSnapshotDict:
    return {
        "id": snapshot.id,
        "drop_point_id": snapshot.drop_point_id,
        "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
        "narrative_score": snapshot.narrative_score,
        "velocity_score": snapshot.velocity_score,
        "spread_score": snapshot.spread_score,
    }


def save_calculation(
    db: Session,
    metric_name: str,
    value: float,
    user_id: str | None = None,
) -> CalculationResult | None:
    """Persist one analytics calculation result row."""
    return _call_with_circuit_breaker(
        "save_calculation",
        None,
        lambda: _save_calculation(db, metric_name, value, user_id=user_id),
    )


def get_user_kpi_snapshot(user_id: str, db: Session) -> UserKpiSnapshotDict | None:
    """Return the latest KPI snapshot for one user."""
    return _call_with_circuit_breaker(
        "get_user_kpi_snapshot",
        None,
        lambda: _get_user_kpi_snapshot(user_id, db),
    )


def run_infinity_orchestrator(
    user_id: str,
    trigger_event: str,
    db: Session,
) -> InfinityOrchestratorResult:
    """Execute the analytics infinity orchestrator for one trigger event."""
    return _call_with_circuit_breaker(
        "run_infinity_orchestrator",
        {},
        lambda: _run_infinity_orchestrator(user_id, trigger_event, db),
    )


def get_user_score(user_id: str, db: Session) -> UserScoreDict | None:
    """Return the latest stored user score row as a plain dict."""
    def _run() -> UserScoreDict | None:
        from apps.analytics.models import UserScore

        user_db_id = parse_user_id(user_id)
        if user_db_id is None:
            return None
        score = db.query(UserScore).filter(UserScore.user_id == user_db_id).first()
        return _score_row_to_dict(score) if score else None

    return _call_with_circuit_breaker("get_user_score", None, _run)


def get_user_scores(user_ids: list[str], db: Session) -> dict[str, UserScoreDict]:
    """Return the latest stored score rows for a batch of user IDs."""
    def _run() -> dict[str, UserScoreDict]:
        from apps.analytics.models import UserScore

        if not user_ids:
            return {}
        uuid_ids = [parse_user_id(user_id) for user_id in user_ids]
        filtered_ids = [user_id for user_id in uuid_ids if user_id is not None]
        if not filtered_ids:
            return {}
        rows = db.query(UserScore).filter(UserScore.user_id.in_(filtered_ids)).all()
        return {str(row.user_id): _score_row_to_dict(row) for row in rows}

    return _call_with_circuit_breaker("get_user_scores", {}, _run)


def get_score_snapshot(drop_point_id: str, db: Session) -> ScoreSnapshotDict | None:
    """Return the newest score snapshot for one drop point."""
    def _run() -> ScoreSnapshotDict | None:
        from apps.analytics.models import ScoreSnapshotDB

        snapshot = (
            db.query(ScoreSnapshotDB)
            .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
            .order_by(ScoreSnapshotDB.timestamp.desc())
            .limit(1)
            .first()
        )
        return _score_snapshot_to_dict(snapshot) if snapshot else None

    return _call_with_circuit_breaker("get_score_snapshot", None, _run)


def list_score_snapshots(
    drop_point_id: str,
    db: Session,
    *,
    limit: int | None = None,
    ascending: bool = False,
    after_timestamp: datetime | None = None,
) -> list[ScoreSnapshotDict]:
    """List score snapshots for one drop point."""
    def _run() -> list[ScoreSnapshotDict]:
        from apps.analytics.models import ScoreSnapshotDB

        query = db.query(ScoreSnapshotDB).filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        if after_timestamp is not None:
            query = query.filter(ScoreSnapshotDB.timestamp > after_timestamp)
        order_col = ScoreSnapshotDB.timestamp.asc() if ascending else ScoreSnapshotDB.timestamp.desc()
        query = query.order_by(order_col)
        if limit is not None:
            query = query.limit(limit)
        return [_score_snapshot_to_dict(row) for row in query.all()]

    return _call_with_circuit_breaker("list_score_snapshots", [], _run)


def list_score_snapshot_drop_point_ids(db: Session, *, min_count: int = 2) -> list[str]:
    """List drop point IDs with at least ``min_count`` score snapshots."""
    def _run() -> list[str]:
        from sqlalchemy import func

        from apps.analytics.models import ScoreSnapshotDB

        rows = (
            db.query(ScoreSnapshotDB.drop_point_id)
            .group_by(ScoreSnapshotDB.drop_point_id)
            .having(func.count(ScoreSnapshotDB.id) >= min_count)
            .all()
        )
        return [row[0] for row in rows]

    return _call_with_circuit_breaker("list_score_snapshot_drop_point_ids", [], _run)


def create_score_snapshot(
    *,
    drop_point_id: str,
    db: Session,
    narrative_score: float,
    velocity_score: float,
    spread_score: float,
    timestamp: datetime | None = None,
    snapshot_id: str | None = None,
) -> ScoreSnapshotDict:
    """Create and flush one score snapshot row, then return its plain dict form."""
    def _run() -> ScoreSnapshotDict:
        from apps.analytics.models import ScoreSnapshotDB

        snapshot = ScoreSnapshotDB(
            id=snapshot_id or str(uuid.uuid4()),
            drop_point_id=drop_point_id,
            timestamp=timestamp,
            narrative_score=narrative_score,
            velocity_score=velocity_score,
            spread_score=spread_score,
        )
        db.add(snapshot)
        db.flush()
        return _score_snapshot_to_dict(snapshot)

    return _call_with_circuit_breaker("create_score_snapshot", {}, _run)


__all__ = [
    "save_calculation",
    "get_user_kpi_snapshot",
    "run_infinity_orchestrator",
    "get_user_score",
    "get_user_scores",
    "get_score_snapshot",
    "list_score_snapshots",
    "list_score_snapshot_drop_point_ids",
    "create_score_snapshot",
]

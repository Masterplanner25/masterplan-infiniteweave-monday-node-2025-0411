"""Analytics domain syscall handlers."""
from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _session_from_context(ctx: SyscallContext):
    from AINDY.db.database import SessionLocal

    external_db = ctx.metadata.get("_db")
    if external_db is not None:
        return external_db, False
    return SessionLocal(), True


def _handle_get_kpi_snapshot(payload: dict, ctx: SyscallContext) -> dict:
    from apps.analytics.services.infinity_service import get_user_kpi_snapshot

    user_id = str(payload["user_id"])
    db, owns_session = _session_from_context(ctx)
    try:
        return get_user_kpi_snapshot(user_id, db) or {}
    finally:
        if owns_session:
            db.close()


def _handle_save_calculation(payload: dict, ctx: SyscallContext) -> dict:
    from apps.analytics.services.calculation_services import save_calculation

    db, owns_session = _session_from_context(ctx)
    try:
        result = save_calculation(
            db=db,
            metric_name=payload["metric_name"],
            value=payload["value"],
            user_id=payload.get("user_id"),
        )
        return {
            "saved": result is not None,
            "id": getattr(result, "id", None),
        }
    finally:
        if owns_session:
            db.close()


def _handle_init_user_score(payload: dict, ctx: SyscallContext) -> dict:
    from apps.analytics.models import UserScore
    from AINDY.platform_layer.user_ids import parse_user_id

    db, owns_session = _session_from_context(ctx)
    try:
        user_id = parse_user_id(payload["user_id"]) or payload["user_id"]
        score = db.query(UserScore).filter(UserScore.user_id == user_id).first()
        created = False
        if score is None:
            score = UserScore(
                user_id=user_id,
                master_score=0.0,
                execution_speed_score=0.0,
                decision_efficiency_score=0.0,
                ai_productivity_boost_score=0.0,
                focus_quality_score=0.0,
                masterplan_progress_score=0.0,
                confidence="baseline",
                data_points_used=0,
                trigger_event="identity_created",
            )
            db.add(score)
            db.commit()
            db.refresh(score)
            created = True
        return {
            "user_id": str(score.user_id),
            "master_score": float(score.master_score or 0.0),
            "created": created,
        }
    finally:
        if owns_session:
            db.close()


def _handle_score_recalculate(payload: dict, ctx: SyscallContext) -> dict:
    from apps.analytics.services.infinity_orchestrator import execute

    db, owns_session = _session_from_context(ctx)
    try:
        result = execute(
            user_id=ctx.user_id,
            db=db,
            trigger_event=payload.get("trigger_event", "manual"),
        )
        if not result:
            raise ValueError("score calculation returned empty result")
        score_data = result.get("score") or result
        return {"score_recalculate_result": score_data}
    finally:
        if owns_session:
            db.close()


def _handle_execute_infinity(payload: dict, ctx: SyscallContext) -> dict:
    from apps.analytics.services.infinity_orchestrator import execute

    db, owns_session = _session_from_context(ctx)
    try:
        result = execute(
            user_id=payload.get("user_id") or ctx.user_id,
            db=db,
            trigger_event=payload.get("trigger_event", "manual"),
        )
        if not result:
            raise ValueError("infinity orchestration returned empty result")
        return result
    finally:
        if owns_session:
            db.close()


def _handle_get_latest_adjustment(payload: dict, ctx: SyscallContext) -> dict:
    from apps.analytics.services.infinity_loop import get_latest_adjustment, serialize_adjustment

    user_id = str(payload.get("user_id") or ctx.user_id or "")
    if not user_id:
        raise ValueError("sys.v1.analytics.get_latest_adjustment requires 'user_id'")

    db, owns_session = _session_from_context(ctx)
    try:
        latest = get_latest_adjustment(user_id=user_id, db=db)
        return {"adjustment": serialize_adjustment(latest)}
    finally:
        if owns_session:
            db.close()


def register_analytics_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.analytics.get_kpi_snapshot",
        handler=_handle_get_kpi_snapshot,
        capability="analytics.read",
        description="Return the KPI snapshot for the given user.",
        input_schema={
            "required": ["user_id"],
            "properties": {
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "properties": {
                "master_score": {"type": "number"},
                "execution_speed": {"type": "number"},
                "decision_efficiency": {"type": "number"},
                "ai_productivity_boost": {"type": "number"},
                "focus_quality": {"type": "number"},
                "masterplan_progress": {"type": "number"},
            },
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.analytics.save_calculation",
        handler=_handle_save_calculation,
        capability="analytics.write",
        description="Persist a calculation result through the analytics domain.",
        input_schema={
            "required": ["metric_name", "value"],
            "properties": {
                "metric_name": {"type": "string"},
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["saved"],
            "properties": {
                "saved": {"type": "bool"},
                "id": {"type": "integer"},
            },
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.analytics.init_user_score",
        handler=_handle_init_user_score,
        capability="analytics.write",
        description="Ensure the analytics UserScore row exists for the given user.",
        input_schema={
            "required": ["user_id"],
            "properties": {
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["user_id", "master_score", "created"],
            "properties": {
                "user_id": {"type": "string"},
                "master_score": {"type": "number"},
                "created": {"type": "bool"},
            },
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.score.recalculate",
        handler=_handle_score_recalculate,
        capability="score.recalculate",
        description="Recalculate the Infinity Score.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.analytics.execute_infinity",
        handler=_handle_execute_infinity,
        capability="score.recalculate",
        description="Run the full infinity orchestration result.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.analytics.get_latest_adjustment",
        handler=_handle_get_latest_adjustment,
        capability="analytics.read",
        description="Return the latest serialized adjustment for the given user.",
        stable=False,
    )
    logger.info(
        "[analytics_syscalls] registered KPI snapshot, calculation persistence, and user score init syscalls"
    )

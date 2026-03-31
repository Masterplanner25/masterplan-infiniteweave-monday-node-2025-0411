from fastapi import APIRouter, Depends, HTTPException, Request
import uuid
from typing import Optional, Literal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline

from db.database import get_db
from db.models.user_score import UserScore, ScoreHistory, KPI_WEIGHTS
from services.auth_service import get_current_user


router = APIRouter(prefix="/scores", tags=["Infinity Score"])


class FeedbackRequest(BaseModel):
    source_type: Literal["arm", "agent", "manual"]
    source_id: Optional[str] = None
    feedback_value: int = Field(..., ge=-1, le=1)
    feedback_text: Optional[str] = None
    loop_adjustment_id: Optional[str] = None


def _latest_adjustment_payload(user_id: str, db: Session):
    from services.infinity_loop import get_latest_adjustment, serialize_adjustment

    latest = get_latest_adjustment(user_id=user_id, db=db)
    serialized = serialize_adjustment(latest)
    if not serialized:
        return None
    return {
        "decision_type": serialized["decision_type"],
        "applied_at": serialized["applied_at"],
        "adjustment_payload": serialized["adjustment_payload"],
    }


def _latest_memory_visibility(user_id: str, db: Session):
    latest = _latest_adjustment_payload(user_id=user_id, db=db)
    payload = (latest or {}).get("adjustment_payload") or {}
    loop_context = payload.get("loop_context") or {}
    memory_signals = list(loop_context.get("memory_signals") or [])
    return {
        "memory_context_count": len(loop_context.get("memory") or []),
        "memory_signal_count": len(memory_signals),
    }


def _score_to_response(score: UserScore, user_id: str, db: Session):
    memory_visibility = _latest_memory_visibility(user_id=user_id, db=db)
    return {
        "user_id": user_id,
        "master_score": score.master_score,
        "kpis": {
            "execution_speed": score.execution_speed_score,
            "decision_efficiency": score.decision_efficiency_score,
            "ai_productivity_boost": score.ai_productivity_boost_score,
            "focus_quality": score.focus_quality_score,
            "masterplan_progress": score.masterplan_progress_score,
        },
        "weights": KPI_WEIGHTS,
        "metadata": {
            "confidence": score.confidence,
            "data_points_used": score.data_points_used,
            "trigger_event": score.trigger_event,
            "calculated_at": (
                score.calculated_at.isoformat() if score.calculated_at else None
            ),
            "memory_context_count": memory_visibility["memory_context_count"],
            "memory_signal_count": memory_visibility["memory_signal_count"],
        },
        "latest_adjustment": _latest_adjustment_payload(user_id=user_id, db=db),
    }


# ------------------------------
# GET SCORE
# ------------------------------
@router.get("/me")
async def get_my_score(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        user_id = uuid.UUID(str(current_user["sub"]))

        score = db.query(UserScore).filter(UserScore.user_id == user_id).first()

        if not score:
            from services.infinity_orchestrator import execute as execute_infinity_orchestrator

            result = execute_infinity_orchestrator(
                user_id=user_id, db=db, trigger_event="manual"
            )

            if result:
                return result["score"]

            return {
                "user_id": str(user_id),
                "master_score": 0.0,
                "kpis": {},
                "message": "No score yet.",
            }

        return _score_to_response(score, str(user_id), db)

    return execute_with_pipeline(request, "scores_get_me", handler)


# ------------------------------
# RECALCULATE
# ------------------------------
@router.post("/me/recalculate")
async def recalculate_my_score(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        from services.infinity_orchestrator import execute as execute_infinity_orchestrator

        result = execute_infinity_orchestrator(
            user_id=uuid.UUID(str(current_user["sub"])),
            db=db,
            trigger_event="manual",
        )

        if not result:
            raise HTTPException(status_code=500, detail="Score calculation failed")

        return result["score"]

    return execute_with_pipeline(request, "scores_recalculate", handler)


# ------------------------------
# HISTORY
# ------------------------------
@router.get("/me/history")
async def get_score_history(
    request: Request,
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        user_id = uuid.UUID(str(current_user["sub"]))

        history = (
            db.query(ScoreHistory)
            .filter(ScoreHistory.user_id == user_id)
            .order_by(ScoreHistory.calculated_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "user_id": str(user_id),
            "history": [
                {
                    "master_score": h.master_score,
                    "calculated_at": (
                        h.calculated_at.isoformat() if h.calculated_at else None
                    ),
                }
                for h in history
            ],
        }

    return execute_with_pipeline(request, "scores_history", handler)


# ------------------------------
# FEEDBACK
# ------------------------------
@router.post("/feedback")
async def record_score_feedback(
    request: Request,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        from db.models.infinity_loop import UserFeedback

        user_id = uuid.UUID(str(current_user["sub"]))

        feedback = UserFeedback(
            user_id=user_id,
            source_type=body.source_type,
            source_id=body.source_id,
            feedback_value=body.feedback_value,
            feedback_text=body.feedback_text,
            loop_adjustment_id=body.loop_adjustment_id,
        )

        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        return {"id": str(feedback.id)}

    return execute_with_pipeline(request, "scores_feedback", handler)


@router.get("/feedback")
async def get_score_feedback(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        from db.models.infinity_loop import UserFeedback

        user_id = uuid.UUID(str(current_user["sub"]))

        history = (
            db.query(UserFeedback)
            .filter(UserFeedback.user_id == user_id)
            .order_by(UserFeedback.created_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "user_id": str(user_id),
            "count": len(history),
        }

    return execute_with_pipeline(request, "scores_feedback_list", handler)
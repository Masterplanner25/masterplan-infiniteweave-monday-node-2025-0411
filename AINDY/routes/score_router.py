"""
Score Router — Infinity Algorithm score endpoints.

GET  /scores/me               — latest cached score + 5 KPI breakdown
POST /scores/me/recalculate   — force full recalculation
GET  /scores/me/history       — score history (reverse chronological)
POST /scores/feedback         — explicit ARM / agent / manual feedback
GET  /scores/feedback         — explicit feedback history
"""
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.user_score import UserScore, ScoreHistory, KPI_WEIGHTS
from services.auth_service import get_current_user

router = APIRouter(
    prefix="/scores",
    tags=["Infinity Score"],
)


class FeedbackRequest(BaseModel):
    source_type: Literal["arm", "agent", "manual"]
    source_id: Optional[str] = None
    feedback_value: int = Field(..., ge=-1, le=1)
    feedback_text: Optional[str] = None
    loop_adjustment_id: Optional[str] = None


def _latest_adjustment_payload(user_id: str, db: Session) -> dict | None:
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


def _score_to_response(score: UserScore, user_id: str, db: Session) -> dict:
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
        },
        "latest_adjustment": _latest_adjustment_payload(user_id=user_id, db=db),
    }


@router.get("/me")
async def get_my_score(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the current user's Infinity score.
    Returns latest cached score with all 5 KPIs.
    If no score exists, calculates one on the fly.
    """
    user_id = str(current_user["sub"])

    score = db.query(UserScore).filter(UserScore.user_id == user_id).first()

    if not score:
        from services.infinity_service import calculate_infinity_score
        from services.infinity_loop import run_loop

        result = calculate_infinity_score(
            user_id=user_id, db=db, trigger_event="manual"
        )
        if result:
            run_loop(user_id=user_id, trigger_event="manual", db=db)
            result["latest_adjustment"] = _latest_adjustment_payload(user_id=user_id, db=db)
            return result
        return {
            "user_id": user_id,
            "master_score": 0.0,
            "kpis": {
                "execution_speed": 0.0,
                "decision_efficiency": 0.0,
                "ai_productivity_boost": 0.0,
                "focus_quality": 0.0,
                "masterplan_progress": 0.0,
            },
            "message": (
                "No score yet. Complete tasks, run ARM analyses, "
                "and start focus sessions to build your Infinity score."
            ),
            "latest_adjustment": None,
        }

    return _score_to_response(score=score, user_id=user_id, db=db)


@router.post("/me/recalculate")
async def recalculate_my_score(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Force recalculation of the current user's Infinity score.
    Use after significant activity to refresh immediately.
    """
    from services.infinity_service import calculate_infinity_score
    from services.infinity_loop import run_loop

    result = calculate_infinity_score(
        user_id=str(current_user["sub"]),
        db=db,
        trigger_event="manual",
    )

    if not result:
        raise HTTPException(status_code=500, detail="Score calculation failed")

    run_loop(user_id=str(current_user["sub"]), trigger_event="manual", db=db)
    result["latest_adjustment"] = _latest_adjustment_payload(
        user_id=str(current_user["sub"]),
        db=db,
    )
    return result


@router.get("/me/history")
async def get_score_history(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get score history for the current user.
    Returns entries in reverse chronological order.
    """
    user_id = str(current_user["sub"])

    history = (
        db.query(ScoreHistory)
        .filter(ScoreHistory.user_id == user_id)
        .order_by(ScoreHistory.calculated_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "user_id": user_id,
        "history": [
            {
                "master_score": h.master_score,
                "kpis": {
                    "execution_speed": h.execution_speed_score,
                    "decision_efficiency": h.decision_efficiency_score,
                    "ai_productivity_boost": h.ai_productivity_boost_score,
                    "focus_quality": h.focus_quality_score,
                    "masterplan_progress": h.masterplan_progress_score,
                },
                "score_delta": h.score_delta,
                "trigger_event": h.trigger_event,
                "calculated_at": (
                    h.calculated_at.isoformat() if h.calculated_at else None
                ),
            }
            for h in history
        ],
        "count": len(history),
    }


@router.post("/feedback")
async def record_score_feedback(
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from datetime import datetime, timezone

    from db.models.infinity_loop import LoopAdjustment, UserFeedback

    user_id = str(current_user["sub"])
    feedback = UserFeedback(
        user_id=user_id,
        source_type=body.source_type,
        source_id=body.source_id,
        feedback_value=body.feedback_value,
        feedback_text=body.feedback_text,
        loop_adjustment_id=body.loop_adjustment_id,
    )
    db.add(feedback)

    if body.loop_adjustment_id:
        try:
            adjustment_uuid = uuid.UUID(body.loop_adjustment_id)
        except ValueError:
            adjustment_uuid = None
        if adjustment_uuid:
            adjustment = (
                db.query(LoopAdjustment)
                .filter(
                    LoopAdjustment.id == adjustment_uuid,
                    LoopAdjustment.user_id == user_id,
                )
                .first()
            )
            if adjustment:
                adjustment.evaluated_at = datetime.now(timezone.utc)
                db.add(adjustment)

    db.commit()
    db.refresh(feedback)

    return {
        "id": str(feedback.id),
        "user_id": feedback.user_id,
        "source_type": feedback.source_type,
        "source_id": feedback.source_id,
        "feedback_value": feedback.feedback_value,
        "feedback_text": feedback.feedback_text,
        "loop_adjustment_id": feedback.loop_adjustment_id,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }


@router.get("/feedback")
async def get_score_feedback(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from db.models.infinity_loop import UserFeedback

    user_id = str(current_user["sub"])
    history = (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == user_id)
        .order_by(UserFeedback.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "user_id": user_id,
        "feedback": [
            {
                "id": str(item.id),
                "source_type": item.source_type,
                "source_id": item.source_id,
                "feedback_value": item.feedback_value,
                "feedback_text": item.feedback_text,
                "loop_adjustment_id": item.loop_adjustment_id,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in history
        ],
        "count": len(history),
    }

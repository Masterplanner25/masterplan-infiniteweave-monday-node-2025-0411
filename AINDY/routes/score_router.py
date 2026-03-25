"""
Score Router — Infinity Algorithm score endpoints.

GET  /scores/me               — latest cached score + 5 KPI breakdown
POST /scores/me/recalculate   — force full recalculation
GET  /scores/me/history       — score history (reverse chronological)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.user_score import UserScore, ScoreHistory, KPI_WEIGHTS
from services.auth_service import get_current_user

router = APIRouter(
    prefix="/scores",
    tags=["Infinity Score"],
)


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
        result = calculate_infinity_score(
            user_id=user_id, db=db, trigger_event="manual"
        )
        if result:
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
        }

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
    }


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

    result = calculate_infinity_score(
        user_id=str(current_user["sub"]),
        db=db,
        trigger_event="manual",
    )

    if not result:
        raise HTTPException(status_code=500, detail="Score calculation failed")

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

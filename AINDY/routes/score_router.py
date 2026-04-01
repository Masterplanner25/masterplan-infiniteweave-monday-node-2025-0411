from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional, Literal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline

from db.database import get_db
from services.auth_service import get_current_user


router = APIRouter(prefix="/scores", tags=["Infinity Score"])


class FeedbackRequest(BaseModel):
    source_type: Literal["arm", "agent", "manual"]
    source_id: Optional[str] = None
    feedback_value: int = Field(..., ge=-1, le=1)
    feedback_text: Optional[str] = None
    loop_adjustment_id: Optional[str] = None


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
        from services.flow_engine import run_flow
        result = run_flow("score_get", {}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail="Score fetch failed")
        return result.get("data")

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
        from services.flow_engine import run_flow
        result = run_flow(
            "score_recalculate",
            {},
            db=db,
            user_id=str(current_user["sub"]),
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail="Score recalculation flow failed")
        return result.get("data")

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
        from services.flow_engine import run_flow
        result = run_flow("score_history", {"limit": limit}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail="Score history fetch failed")
        return result.get("data")

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
        from services.flow_engine import run_flow
        result = run_flow(
            "score_feedback",
            {
                "source_type": body.source_type,
                "source_id": body.source_id,
                "feedback_value": body.feedback_value,
                "feedback_text": body.feedback_text,
                "loop_adjustment_id": body.loop_adjustment_id,
            },
            db=db,
            user_id=str(current_user["sub"]),
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail="Score feedback flow failed")
        return result.get("data")

    return execute_with_pipeline(request, "scores_feedback", handler)


@router.get("/feedback")
async def get_score_feedback(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        from services.flow_engine import run_flow
        result = run_flow("score_feedback_list", {"limit": limit}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail="Score feedback list failed")
        return result.get("data")

    return execute_with_pipeline(request, "scores_feedback_list", handler)
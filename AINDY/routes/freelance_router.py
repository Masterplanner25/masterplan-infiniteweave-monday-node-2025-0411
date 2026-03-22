# routes/freelance_router.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.database import get_db
from services import freelance_service
from services.auth_service import get_current_user
from schemas.freelance import (
    FreelanceOrderCreate,
    FreelanceOrderResponse,
    FeedbackCreate,
    FeedbackResponse,
    RevenueMetricsResponse,
)


router = APIRouter(prefix="/freelance", tags=["Freelance"], dependencies=[Depends(get_current_user)])

# -----------------------------------------------------
# 1️⃣  Create a New Order
# -----------------------------------------------------
@router.post("/order", response_model=FreelanceOrderResponse, status_code=status.HTTP_201_CREATED)
def create_freelance_order(
    order: FreelanceOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new freelance order and log it to the Memory Bridge.
    """
    try:
        return freelance_service.create_order(db, order, user_id=str(current_user["sub"]))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "freelance_order_create_failed",
                "message": "Failed to create order",
                "details": str(e),
            },
        )


# -----------------------------------------------------
# 2️⃣  Deliver an Order
# -----------------------------------------------------
@router.post("/deliver/{order_id}", response_model=FreelanceOrderResponse)
def deliver_order(
    order_id: int,
    ai_output: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark an order as delivered and attach the AI-generated output.
    Only the owner of the order can deliver it.
    """
    from db.models.freelance import FreelanceOrder
    order = db.query(FreelanceOrder).filter(
        FreelanceOrder.id == order_id,
        FreelanceOrder.user_id == str(current_user["sub"]),
    ).first()
    if not order:
        raise HTTPException(
            status_code=404,
            detail={"error": "freelance_order_not_found", "message": "Order not found"},
        )
    try:
        return freelance_service.deliver_order(db, order_id, ai_output)
    except ValueError as ve:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "freelance_order_not_found",
                "message": "Order not found",
                "details": str(ve),
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "freelance_order_deliver_failed",
                "message": "Failed to deliver order",
                "details": str(e),
            },
        )


# -----------------------------------------------------
# 3️⃣  Collect Feedback
# -----------------------------------------------------
@router.post("/feedback", response_model=FeedbackResponse)
def collect_feedback(
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Collect client feedback and store summarized version.
    """
    try:
        return freelance_service.collect_feedback(db, feedback, user_id=str(current_user["sub"]))
    except ValueError as ve:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "freelance_feedback_not_found",
                "message": "Feedback target not found",
                "details": str(ve),
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "freelance_feedback_collect_failed",
                "message": "Failed to collect feedback",
                "details": str(e),
            },
        )


# -----------------------------------------------------
# 4️⃣  Retrieve All Orders (scoped to current user)
# -----------------------------------------------------
@router.get("/orders", response_model=list[FreelanceOrderResponse])
def get_all_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieve all freelance orders belonging to the current user.
    """
    return freelance_service.get_all_orders(db, user_id=str(current_user["sub"]))


# -----------------------------------------------------
# 5️⃣  Retrieve All Feedback (scoped to current user)
# -----------------------------------------------------
@router.get("/feedback", response_model=list[FeedbackResponse])
def get_all_feedback(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieve all client feedback records belonging to the current user.
    """
    return freelance_service.get_all_feedback(db, user_id=str(current_user["sub"]))


# -----------------------------------------------------
# 6️⃣  Retrieve Latest Revenue Metrics
# -----------------------------------------------------
@router.get("/metrics/latest", response_model=RevenueMetricsResponse)
def get_latest_metrics(db: Session = Depends(get_db)):
    """
    Retrieve the most recent revenue metrics record (system-wide aggregate).
    """
    metric = freelance_service.get_latest_metrics(db)
    if not metric:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "revenue_metrics_not_found",
                "message": "No revenue metrics found",
            },
        )
    return metric


# -----------------------------------------------------
# 7️⃣  Trigger Metrics Update
# -----------------------------------------------------
@router.post("/metrics/update", response_model=RevenueMetricsResponse)
def update_metrics(db: Session = Depends(get_db)):
    """
    Manually trigger a recalculation of revenue metrics (system-wide aggregate).
    """
    try:
        return freelance_service.update_revenue_metrics(db)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "revenue_metrics_update_failed",
                "message": "Metrics update failed",
                "details": str(e),
            },
        )

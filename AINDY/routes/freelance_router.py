# routes/freelance_router.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.database import get_db
from services import freelance_service
from schemas.freelance import (
    FreelanceOrderCreate,
    FreelanceOrderResponse,
    FeedbackCreate,
    FeedbackResponse,
    RevenueMetricsResponse,
)


router = APIRouter(prefix="/freelance", tags=["Freelance"])

# -----------------------------------------------------
# 1️⃣  Create a New Order
# -----------------------------------------------------
@router.post("/order", response_model=FreelanceOrderResponse, status_code=status.HTTP_201_CREATED)
def create_freelance_order(order: FreelanceOrderCreate, db: Session = Depends(get_db)):
    """
    Create a new freelance order and log it to the Memory Bridge.
    """
    try:
        return freelance_service.create_order(db, order)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create order: {e}")


# -----------------------------------------------------
# 2️⃣  Deliver an Order
# -----------------------------------------------------
@router.post("/deliver/{order_id}", response_model=FreelanceOrderResponse)
def deliver_order(order_id: int, ai_output: str, db: Session = Depends(get_db)):
    """
    Mark an order as delivered and attach the AI-generated output.
    """
    try:
        return freelance_service.deliver_order(db, order_id, ai_output)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deliver order: {e}")


# -----------------------------------------------------
# 3️⃣  Collect Feedback
# -----------------------------------------------------
@router.post("/feedback", response_model=FeedbackResponse)
def collect_feedback(feedback: FeedbackCreate, db: Session = Depends(get_db)):
    """
    Collect client feedback and store summarized version.
    """
    try:
        return freelance_service.collect_feedback(db, feedback)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect feedback: {e}")


# -----------------------------------------------------
# 4️⃣  Retrieve All Orders
# -----------------------------------------------------
@router.get("/orders", response_model=list[FreelanceOrderResponse])
def get_all_orders(db: Session = Depends(get_db)):
    """
    Retrieve all freelance orders.
    """
    return freelance_service.get_all_orders(db)


# -----------------------------------------------------
# 5️⃣  Retrieve All Feedback
# -----------------------------------------------------
@router.get("/feedback", response_model=list[FeedbackResponse])
def get_all_feedback(db: Session = Depends(get_db)):
    """
    Retrieve all client feedback records.
    """
    return freelance_service.get_all_feedback(db)


# -----------------------------------------------------
# 6️⃣  Retrieve Latest Revenue Metrics
# -----------------------------------------------------
@router.get("/metrics/latest", response_model=RevenueMetricsResponse)
def get_latest_metrics(db: Session = Depends(get_db)):
    """
    Retrieve the most recent revenue metrics record.
    """
    metric = freelance_service.get_latest_metrics(db)
    if not metric:
        raise HTTPException(status_code=404, detail="No revenue metrics found.")
    return metric


# -----------------------------------------------------
# 7️⃣  Trigger Metrics Update
# -----------------------------------------------------
@router.post("/metrics/update", response_model=RevenueMetricsResponse)
def update_metrics(db: Session = Depends(get_db)):
    """
    Manually trigger a recalculation of revenue metrics.
    """
    try:
        return freelance_service.update_revenue_metrics(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics update failed: {e}")

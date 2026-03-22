# services/freelance_service.py

from datetime import datetime
import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# ORM models (database layer)
from db.models.freelance import (
    FreelanceOrder,
    ClientFeedback,
    RevenueMetrics,
)

# Pydantic schemas (validation layer)
from schemas.freelance import (
    FreelanceOrderCreate,
    FeedbackCreate,
)

from services.memory_capture_engine import MemoryCaptureEngine

logger = logging.getLogger(__name__)

# -----------------------------------------------------
# Core Freelance Order Logic
# -----------------------------------------------------

def create_order(db: Session, order_data: FreelanceOrderCreate, user_id: str = None):
    """
    Creates a new freelance order and logs it to the Memory Bridge.
    """
    try:
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
        order = FreelanceOrder(
            client_name=order_data.client_name,
            client_email=order_data.client_email,
            service_type=order_data.service_type,
            project_details=order_data.project_details,
            price=order_data.price,
            status="pending",
            user_id=user_uuid,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # 🔗 Log to Memory Bridge
        try:
            engine = MemoryCaptureEngine(
                db=db,
                user_id=str(user_id) if user_id else None,
                agent_namespace="freelance",
            )
            engine.evaluate_and_capture(
                event_type="freelance_order",
                content=f"New Freelance Order: {order.service_type} for {order.client_name}",
                source="freelance_service",
                tags=["freelance", "order", order.service_type],
                node_type="outcome",
                extra={"client_email": order.client_email, "price": order.price},
            )
        except Exception as bridge_err:
            logger.warning("[MemoryBridge] Failed to log freelance order: %s", bridge_err)

        logger.info("Created freelance order #%s for %s", order.id, order.client_name)
        return order

    except SQLAlchemyError as e:
        db.rollback()
        logger.warning("[DB Error] create_order: %s", e)
        raise


def deliver_order(db: Session, order_id: int, ai_output: str):
    """
    Marks an order as delivered and updates AI output.
    """
    order = db.query(FreelanceOrder).filter(FreelanceOrder.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")

    order.ai_output = ai_output
    order.status = "delivered"
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)

    # Log delivery to Memory Bridge
    try:
        engine = MemoryCaptureEngine(
            db=db,
            user_id=str(order.user_id) if order.user_id else None,
            agent_namespace="freelance",
        )
        engine.evaluate_and_capture(
            event_type="freelance_delivery",
            content=f"Delivered Order #{order.id}: {order.service_type}",
            source="freelance_service",
            tags=["freelance", "delivery", order.service_type],
            node_type="outcome",
            extra={"client_name": order.client_name, "price": order.price},
        )
    except Exception as bridge_err:
        logger.warning("[MemoryBridge] Delivery log error: %s", bridge_err)

    logger.info("Delivered order #%s", order.id)
    return order


def collect_feedback(db: Session, feedback_data: FeedbackCreate, user_id: str = None):
    """
    Records client feedback and summarizes it for future optimization.
    """
    order = db.query(FreelanceOrder).filter(FreelanceOrder.id == feedback_data.order_id).first()
    if not order:
        raise ValueError(f"Order {feedback_data.order_id} not found")

    user_uuid = uuid.UUID(str(user_id)) if user_id else None
    feedback = ClientFeedback(
        order_id=feedback_data.order_id,
        rating=feedback_data.rating,
        feedback_text=feedback_data.feedback_text,
        ai_summary=None,
        user_id=user_uuid,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # Optional: Generate AI summary (placeholder for GPT integration)
    summary = (
        f"Client rated {feedback.rating}/5. "
        f"Feedback: {feedback.feedback_text[:150]}..."
        if feedback.feedback_text else "No text feedback provided."
    )
    feedback.ai_summary = summary
    db.commit()

    # Log feedback to Memory Bridge
    try:
        engine = MemoryCaptureEngine(
            db=db,
            user_id=str(user_id) if user_id else None,
            agent_namespace="freelance",
        )
        engine.evaluate_and_capture(
            event_type="freelance_feedback",
            content=f"Feedback for Order #{feedback.order_id}: {summary}",
            source="freelance_service",
            tags=["freelance", "feedback", order.service_type],
            node_type="insight",
            extra={"rating": feedback.rating},
        )
    except Exception as bridge_err:
        logger.warning("[MemoryBridge] Feedback log error: %s", bridge_err)

    logger.info("Collected feedback for order #%s", order.id)
    return feedback


# -----------------------------------------------------
# Revenue Metrics
# -----------------------------------------------------

def update_revenue_metrics(db: Session):
    """
    Calculates and stores cumulative revenue and basic performance metrics.
    """
    total_revenue = (
        db.query(FreelanceOrder)
        .filter(FreelanceOrder.status == "delivered")
        .with_entities(FreelanceOrder.price)
        .all()
    )
    total = sum([p[0] for p in total_revenue]) if total_revenue else 0.0

    metric = RevenueMetrics(
        total_revenue=total,
        avg_execution_time=None,  # can be extended with delivery timestamps
        income_efficiency=None,
        ai_productivity_boost=None,
    )
    db.add(metric)
    db.commit()

    logger.info("Revenue metrics updated: Total Revenue = $%.2f", total)
    return metric


# -----------------------------------------------------
# Helper: Get all orders / feedback / metrics
# -----------------------------------------------------

def get_all_orders(db: Session, user_id: str = None):
    q = db.query(FreelanceOrder)
    if user_id:
        q = q.filter(FreelanceOrder.user_id == uuid.UUID(str(user_id)))
    return q.order_by(FreelanceOrder.created_at.desc()).all()


def get_all_feedback(db: Session, user_id: str = None):
    q = db.query(ClientFeedback)
    if user_id:
        q = q.filter(ClientFeedback.user_id == uuid.UUID(str(user_id)))
    return q.order_by(ClientFeedback.created_at.desc()).all()


def get_latest_metrics(db: Session):
    return db.query(RevenueMetrics).order_by(RevenueMetrics.date.desc()).first()

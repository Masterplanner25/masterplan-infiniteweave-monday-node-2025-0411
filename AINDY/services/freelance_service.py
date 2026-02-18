# services/freelance_service.py

from datetime import datetime
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

from services.memory_persistence import MemoryNodeDAO


# -----------------------------------------------------
# Core Freelance Order Logic
# -----------------------------------------------------

def create_order(db: Session, order_data: FreelanceOrderCreate):
    """
    Creates a new freelance order and logs it to the Memory Bridge.
    """
    try:
        order = FreelanceOrder(
            client_name=order_data.client_name,
            client_email=order_data.client_email,
            service_type=order_data.service_type,
            project_details=order_data.project_details,
            price=order_data.price,
            status="pending",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # 🔗 Log to Memory Bridge
        try:
            dao = MemoryNodeDAO(db)
            dao.save_memory_node(
                type("MemoryNode", (), {
                    "content": f"New Freelance Order: {order.service_type} for {order.client_name}",
                    "tags": ["freelance", "order", order.service_type],
                    "node_type": "freelance_order",
                    "extra": {"client_email": order.client_email, "price": order.price},
                })()
            )
        except Exception as bridge_err:
            print(f"[MemoryBridge] Failed to log freelance order: {bridge_err}")

        print(f"✅ Created freelance order #{order.id} for {order.client_name}")
        return order

    except SQLAlchemyError as e:
        db.rollback()
        print(f"[DB Error] create_order: {e}")
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
        dao = MemoryNodeDAO(db)
        dao.save_memory_node(
            type("MemoryNode", (), {
                "content": f"Delivered Order #{order.id}: {order.service_type}",
                "tags": ["freelance", "delivery", order.service_type],
                "node_type": "freelance_delivery",
                "extra": {"client_name": order.client_name, "price": order.price},
            })()
        )
    except Exception as bridge_err:
        print(f"[MemoryBridge] Delivery log error: {bridge_err}")

    print(f"📦 Delivered order #{order.id}")
    return order


def collect_feedback(db: Session, feedback_data: FeedbackCreate):
    """
    Records client feedback and summarizes it for future optimization.
    """
    order = db.query(FreelanceOrder).filter(FreelanceOrder.id == feedback_data.order_id).first()
    if not order:
        raise ValueError(f"Order {feedback_data.order_id} not found")

    feedback = ClientFeedback(
        order_id=feedback_data.order_id,
        rating=feedback_data.rating,
        feedback_text=feedback_data.feedback_text,
        ai_summary=None,
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
        dao = MemoryNodeDAO(db)
        dao.save_memory_node(
            type("MemoryNode", (), {
                "content": f"Feedback for Order #{feedback.order_id}: {summary}",
                "tags": ["freelance", "feedback", order.service_type],
                "node_type": "freelance_feedback",
                "extra": {"rating": feedback.rating},
            })()
        )
    except Exception as bridge_err:
        print(f"[MemoryBridge] Feedback log error: {bridge_err}")

    print(f"💬 Collected feedback for order #{order.id}")
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

    print(f"📈 Revenue metrics updated: Total Revenue = ${total:.2f}")
    return metric


# -----------------------------------------------------
# Helper: Get all orders / feedback / metrics
# -----------------------------------------------------

def get_all_orders(db: Session):
    return db.query(FreelanceOrder).order_by(FreelanceOrder.created_at.desc()).all()


def get_all_feedback(db: Session):
    return db.query(ClientFeedback).order_by(ClientFeedback.created_at.desc()).all()


def get_latest_metrics(db: Session):
    return db.query(RevenueMetrics).order_by(RevenueMetrics.date.desc()).first()

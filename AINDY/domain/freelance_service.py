# services/freelance_service.py
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import logging
from openai import OpenAI
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

from domain.automation_execution_service import execute_automation_action
from core.execution_signal_helper import queue_memory_capture, queue_system_event
from platform_layer.external_call_service import perform_external_call
from utils.trace_context import is_pipeline_active
from memory.memory_scoring_service import get_relevant_memories
from core.execution_dispatcher import dispatch_autonomous_job
from core.system_event_service import emit_error_event
from core.system_event_types import SystemEventTypes
from domain.task_services import queue_task_automation

logger = logging.getLogger(__name__)
_client = OpenAI()

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
            masterplan_id=order_data.masterplan_id,
            task_id=order_data.task_id,
            automation_type=order_data.automation_type,
            automation_config=order_data.automation_config,
            delivery_type=order_data.delivery_type or "manual",
            delivery_config=order_data.delivery_config,
            delivery_status="pending",
            started_at=datetime.now(timezone.utc),
            user_id=user_uuid,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        if order_data.auto_generate_delivery:
            queue_delivery_generation(db, order.id, user_id=str(user_uuid) if user_uuid else None)

        # 🔗 Log to Memory Bridge
        try:
            if is_pipeline_active():
                raise RuntimeError("pipeline_active_memory_capture_disabled")
            queue_memory_capture(
                db=db,
                user_id=str(user_id) if user_id else None,
                agent_namespace="freelance",
                event_type="freelance_order",
                content=f"New Freelance Order: {order.service_type} for {order.client_name}",
                source="freelance_service",
                tags=["freelance", "order", order.service_type],
                node_type="outcome",
                extra={"client_email": order.client_email, "price": order.price},
            )
        except Exception as bridge_err:
            if str(bridge_err) == "pipeline_active_memory_capture_disabled":
                pass
            else:
                logger.warning("[MemoryBridge] Failed to log freelance order: %s", bridge_err)

        logger.info("Created freelance order #%s for %s", order.id, order.client_name)
        return order

    except SQLAlchemyError as e:
        db.rollback()
        logger.warning("[DB Error] create_order: %s", e)
        raise


def generate_deliverable(db: Session, order_id: int, user_id: str | None = None) -> FreelanceOrder:
    order = db.query(FreelanceOrder).filter(FreelanceOrder.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")
    user_id = user_id or (str(order.user_id) if order.user_id else None)
    prompt = _build_delivery_prompt(order, db, user_id=user_id)
    response = perform_external_call(
        service_name="openai",
        db=db,
        user_id=user_id,
        endpoint="chat.completions.create",
        model="gpt-4o-mini",
        method="openai.chat",
        extra={"purpose": "freelance_delivery_generation", "order_id": order.id},
        operation=lambda: _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are A.I.N.D.Y. generating a concise professional freelance deliverable. "
                        "Return only the deliverable text, no framing."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        ),
    )
    ai_output = (response.choices[0].message.content or "").strip()
    if not ai_output:
        raise RuntimeError("freelance_delivery_generation_empty")
    return deliver_order(db, order_id, ai_output, generated_by_ai=True)


def deliver_order(db: Session, order_id: int, ai_output: str | None = None, *, generated_by_ai: bool = False):
    """
    Marks an order as delivered and updates AI output.
    """
    order = db.query(FreelanceOrder).filter(FreelanceOrder.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")
    if not ai_output:
        return generate_deliverable(db, order_id, user_id=str(order.user_id) if order.user_id else None)

    order.ai_output = ai_output
    order.updated_at = datetime.now(timezone.utc)
    order.delivery_quality_score = _calculate_delivery_quality(order, ai_output, generated_by_ai=generated_by_ai)
    _perform_delivery(db, order, generated_by_ai=generated_by_ai)

    # Log delivery to Memory Bridge
    try:
        if is_pipeline_active():
            raise RuntimeError("pipeline_active_memory_capture_disabled")
        queue_memory_capture(
            db=db,
            user_id=str(order.user_id) if order.user_id else None,
            agent_namespace="freelance",
            event_type="freelance_delivery",
            content=f"Delivered Order #{order.id}: {order.service_type}",
            source="freelance_service",
            tags=["freelance", "delivery", order.service_type],
            node_type="outcome",
            extra={
                "client_name": order.client_name,
                "price": order.price,
                "delivery_quality_score": order.delivery_quality_score,
                "time_to_completion_seconds": order.time_to_completion_seconds,
                "generated_by_ai": generated_by_ai,
            },
        )
    except Exception as bridge_err:
        if str(bridge_err) != "pipeline_active_memory_capture_disabled":
            logger.warning("[MemoryBridge] Delivery log error: %s", bridge_err)

    _sync_freelance_automation(db, order)
    _update_linked_task_feedback(db, order, outcome="success")

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
        success_signal=_feedback_success_signal(feedback_data.rating),
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
    if feedback.rating is not None:
        order.delivery_quality_score = _blend_quality_with_feedback(
            order.delivery_quality_score,
            feedback.rating,
        )
        order.income_efficiency = _calculate_income_efficiency(order)
    db.commit()

    # Log feedback to Memory Bridge
    try:
        if is_pipeline_active():
            raise RuntimeError("pipeline_active_memory_capture_disabled")
        queue_memory_capture(
            db=db,
            user_id=str(user_id) if user_id else None,
            agent_namespace="freelance",
            event_type="freelance_feedback",
            content=f"Feedback for Order #{feedback.order_id}: {summary}",
            source="freelance_service",
            tags=["freelance", "feedback", order.service_type],
            node_type="insight" if (feedback.rating or 0) >= 3 else "failure",
            extra={"rating": feedback.rating, "success_signal": feedback.success_signal},
        )
    except Exception as bridge_err:
        if str(bridge_err) != "pipeline_active_memory_capture_disabled":
            logger.warning("[MemoryBridge] Feedback log error: %s", bridge_err)

    _update_linked_task_feedback(
        db,
        order,
        outcome="success" if (feedback.rating or 0) >= 4 else "failure" if (feedback.rating or 0) <= 2 else "neutral",
    )

    logger.info("Collected feedback for order #%s", order.id)
    return feedback


# -----------------------------------------------------
# Revenue Metrics
# -----------------------------------------------------

def update_revenue_metrics(db: Session, user_id: str = None):
    """
    Calculates and stores cumulative revenue and basic performance metrics.
    """
    query = db.query(FreelanceOrder).filter(FreelanceOrder.status == "delivered")
    if user_id:
        query = query.filter(FreelanceOrder.user_id == uuid.UUID(str(user_id)))
    delivered_orders = query.all()
    total_revenue = [float(order.price or 0.0) for order in delivered_orders]
    total = sum(total_revenue) if total_revenue else 0.0

    metric = RevenueMetrics(
        total_revenue=total,
        avg_execution_time=_average(
            [order.time_to_completion_seconds for order in delivered_orders if order.time_to_completion_seconds is not None]
        ),
        income_efficiency=_average(
            [order.income_efficiency for order in delivered_orders if order.income_efficiency is not None]
        ),
        ai_productivity_boost=_average(
            [1.0 for order in delivered_orders if order.ai_output]
        ) or 0.0,
        avg_delivery_quality=_average(
            [order.delivery_quality_score for order in delivered_orders if order.delivery_quality_score is not None]
        ),
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


def queue_delivery_generation(db: Session, order_id: int, user_id: str | None = None) -> dict:
    order = db.query(FreelanceOrder).filter(FreelanceOrder.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")
    dr = dispatch_autonomous_job(
        task_name="freelance.generate_delivery",
        payload={"order_id": order.id, "user_id": user_id or (str(order.user_id) if order.user_id else None)},
        user_id=user_id or order.user_id,
        source="freelance_delivery",
        trigger_type="system",
        trigger_context={
            "goal": f"freelance_delivery:{order.service_type}",
            "importance": 0.8,
            "masterplan_id": order.masterplan_id,
        },
    )
    dispatch = dr.envelope
    automation_log_id = (((dispatch or {}).get("result") or {}).get("automation_log_id"))
    if automation_log_id:
        order.automation_log_id = automation_log_id
        db.commit()
        db.refresh(order)
    return dispatch


def update_delivery_config(
    db: Session,
    order_id: int,
    *,
    user_id: str,
    delivery_type: str | None,
    delivery_config: dict | None,
) -> FreelanceOrder:
    order = (
        db.query(FreelanceOrder)
        .filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == uuid.UUID(str(user_id)),
        )
        .first()
    )
    if not order:
        raise ValueError(f"Order {order_id} not found")
    if delivery_type is not None:
        order.delivery_type = delivery_type
    if delivery_config is not None:
        order.delivery_config = delivery_config
    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return order


def _build_delivery_prompt(order: FreelanceOrder, db: Session, user_id: str | None = None) -> str:
    memory_signals = get_relevant_memories(
        {
            "user_id": user_id,
            "trigger_event": "freelance_delivery",
            "goal": order.service_type,
            "current_state": order.project_details or "",
        },
        db=db,
        limit=3,
    )
    prior = "\n".join(
        f"- {signal.get('type')}: {signal.get('cause_summary')} -> {signal.get('outcome')}"
        for signal in memory_signals
    )
    return (
        f"Client: {order.client_name}\n"
        f"Service: {order.service_type}\n"
        f"Project details: {order.project_details or 'No details provided.'}\n"
        f"Budget: {order.price}\n"
        f"Relevant prior outcomes:\n{prior or '- none'}\n\n"
        "Generate the deliverable directly."
    )


def _calculate_time_to_completion(order: FreelanceOrder) -> float | None:
    started_at = order.started_at or order.created_at
    delivered_at = order.delivered_at
    if not started_at or not delivered_at:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=timezone.utc)
    return round(max(0.0, (delivered_at - started_at).total_seconds()), 2)


def _calculate_delivery_quality(order: FreelanceOrder, ai_output: str, *, generated_by_ai: bool) -> float:
    detail_score = min(1.0, len((order.project_details or "").split()) / 80.0)
    output_score = min(1.0, len(ai_output.split()) / 120.0)
    automation_bonus = 0.1 if generated_by_ai else 0.0
    return round(min(1.0, detail_score * 0.45 + output_score * 0.45 + automation_bonus), 3)


def _calculate_income_efficiency(order: FreelanceOrder) -> float | None:
    if not order.time_to_completion_seconds or order.time_to_completion_seconds <= 0:
        return None
    hours = order.time_to_completion_seconds / 3600.0
    return round(order.price / max(hours, 0.1), 2)


def _perform_delivery(db: Session, order: FreelanceOrder, *, generated_by_ai: bool) -> None:
    delivery_type = str(order.delivery_type or "manual").strip().lower() or "manual"
    trace_id = f"freelance-delivery-{order.id}"
    delivery_payload = {
        "order_id": order.id,
        "service_type": order.service_type,
        "client_name": order.client_name,
        "client_email": order.client_email,
        "delivery_type": delivery_type,
    }
    started_event_id = queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_DELIVERY_STARTED,
        user_id=order.user_id,
        trace_id=trace_id,
        parent_event_id=None,
        source="freelance",
        payload=delivery_payload,
        required=True,
    )

    try:
        result = _dispatch_delivery(order, db=db)
        order.external_response = result
        order.delivery_status = str(result.get("status") or "success")
        order.status = "delivered" if order.delivery_status in {"success", "completed", "stubbed", "manual"} else "delivery_failed"
        order.delivered_at = datetime.now(timezone.utc)
        order.time_to_completion_seconds = _calculate_time_to_completion(order)
        order.income_efficiency = _calculate_income_efficiency(order)
        db.commit()
        db.refresh(order)
        queue_system_event(
            db=db,
            event_type=SystemEventTypes.FREELANCE_DELIVERY_COMPLETED,
            user_id=order.user_id,
            trace_id=trace_id,
            parent_event_id=started_event_id,
            source="freelance",
            payload={
                **delivery_payload,
                "delivery_status": order.delivery_status,
                "generated_by_ai": generated_by_ai,
                "external_response": result,
            },
            required=True,
        )
    except Exception as exc:
        order.delivery_status = "failure"
        order.status = "delivery_failed"
        order.external_response = {"error": str(exc)}
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)
        queue_system_event(
            db=db,
            event_type=SystemEventTypes.FREELANCE_DELIVERY_FAILED,
            user_id=order.user_id,
            trace_id=trace_id,
            parent_event_id=started_event_id,
            source="freelance",
            payload={
                **delivery_payload,
                "delivery_status": order.delivery_status,
                "error": str(exc),
            },
            required=True,
        )
        emit_error_event(
            db=db,
            error_type="freelance_delivery",
            message=str(exc),
            user_id=order.user_id,
            trace_id=trace_id,
            parent_event_id=started_event_id,
            source="freelance",
            payload=delivery_payload,
            required=True,
        )
        raise


def _dispatch_delivery(order: FreelanceOrder, *, db: Session) -> dict:
    delivery_type = str(order.delivery_type or "manual").strip().lower() or "manual"
    config = dict(order.delivery_config or {})
    if delivery_type == "manual":
        return {
            "status": "manual",
            "message": "Deliverable generated and stored for manual delivery",
        }

    automation_type = delivery_type
    if delivery_type == "payment":
        automation_type = "stripe"
    elif delivery_type not in {"email", "webhook", "stripe"}:
        raise ValueError(f"unsupported_delivery_type:{delivery_type}")

    config.setdefault("content", order.ai_output)
    config.setdefault("body", order.ai_output)
    config.setdefault("recipient", order.client_email)
    config.setdefault("customer_email", order.client_email)
    config.setdefault("metadata", {"order_id": order.id, "service_type": order.service_type})
    payload = {
        "automation_type": automation_type,
        "automation_config": config,
        "task_name": f"freelance_delivery:{order.service_type}",
        "task_id": order.task_id,
        "masterplan_id": order.masterplan_id,
        "user_id": str(order.user_id) if order.user_id else None,
    }
    return execute_automation_action(payload, db)


def _average(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 3)


def _feedback_success_signal(rating: int | None) -> float | None:
    if rating is None:
        return None
    return round((float(rating) - 3.0) / 2.0, 3)


def _blend_quality_with_feedback(current_quality: float | None, rating: int) -> float:
    rating_quality = max(0.0, min(1.0, float(rating) / 5.0))
    if current_quality is None:
        return round(rating_quality, 3)
    return round(((float(current_quality) * 0.6) + (rating_quality * 0.4)), 3)


def _update_linked_task_feedback(db: Session, order: FreelanceOrder, *, outcome: str) -> None:
    try:
        if not order.task_id or not order.user_id:
            return
        from domain.task_services import get_task_by_id
        task = get_task_by_id(db, order.task_id, str(order.user_id))
        if not task:
            return
        if outcome == "success" and task.status != "completed":
            task.status = "completed"
        elif outcome == "failure" and task.status == "completed":
            task.status = "paused"
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Freelance task feedback sync failed: %s", exc)


def _sync_freelance_automation(db: Session, order: FreelanceOrder) -> None:
    try:
        if not order.task_id or not order.user_id:
            return
        from domain.task_services import get_task_by_id
        task = get_task_by_id(db, order.task_id, str(order.user_id))
        if not task:
            return
        dispatch = queue_task_automation(
            db=db,
            task=task,
            user_id=str(order.user_id),
            reason="freelance_delivery_completed",
        )
        automation_log_id = (((dispatch or {}).get("result") or {}).get("automation_log_id"))
        if automation_log_id:
            order.automation_log_id = automation_log_id
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Freelance automation sync failed: %s", exc)




# services/freelance_service.py
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import logging
import hashlib
import hmac as _hmac
import json as _json
import time as _time
from urllib import parse as _parse
from urllib import request as _req

from sqlalchemy import String, cast
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# ORM models (database layer)
from apps.freelance.models.freelance import (
    ClientFeedback,
    FreelanceOrder,
    PaymentRecord,
    RefundRecord,
    RevenueMetrics,
    WebhookEvent,
)
from apps.freelance.services.idempotency import check_or_create

# Pydantic schemas (validation layer)
from apps.freelance.schemas.freelance import (
    FreelanceOrderCreate,
    FeedbackCreate,
)

from AINDY.platform_layer.app_runtime import (
    dispatch_autonomous_job,
    emit_error_event,
    queue_memory_capture,
    queue_system_event,
)
from apps.freelance.events import FreelanceEventTypes as SystemEventTypes
from AINDY.platform_layer.external_call_service import perform_external_call
from AINDY.platform_layer.trace_context import is_pipeline_active
from AINDY.platform_layer.openai_client import get_openai_client, chat_completion
from AINDY.config import settings
from AINDY.memory.memory_scoring_service import get_relevant_memories

logger = logging.getLogger(__name__)

_SUPPORTED_DELIVERY_TYPES = {"manual", "email", "webhook", "payment", "subscription"}
_SUBSCRIPTION_ACCESS_ACTIVE = {"active", "trialing"}

# -----------------------------------------------------
# Core Freelance Order Logic
# -----------------------------------------------------

def create_order(
    db: Session,
    order_data: FreelanceOrderCreate,
    user_id: str = None,
    *,
    idempotency_key: str | None = None,
    return_created: bool = False,
):
    """
    Creates a new freelance order and logs it to the Memory Bridge.
    """
    try:
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
        delivery_type = str(order_data.delivery_type or "manual").strip().lower()
        if delivery_type not in _SUPPORTED_DELIVERY_TYPES:
            raise ValueError(
                f"delivery_type '{delivery_type}' is not supported. "
                f"Supported types: {sorted(_SUPPORTED_DELIVERY_TYPES)}"
            )
        if idempotency_key:
            order, was_created = check_or_create(
                db,
                FreelanceOrder,
                idempotency_key,
                lambda: _build_order_from_create(order_data, user_uuid, delivery_type),
            )
            if was_created:
                _finalize_created_order(
                    db,
                    order,
                    order_data=order_data,
                    user_id=str(user_uuid) if user_uuid else None,
                )
            logger.info(
                "Created freelance order #%s for %s%s",
                order.id,
                order.client_name,
                "" if was_created else " (idempotent replay)",
            )
            if return_created:
                return order, was_created
            return order
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
            delivery_type=delivery_type,
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
        if return_created:
            return order, True
        return order

    except SQLAlchemyError as e:
        db.rollback()
        logger.warning("[DB Error] create_order: %s", e)
        raise


def _build_order_from_create(
    order_data: FreelanceOrderCreate,
    user_uuid,
    delivery_type: str,
) -> FreelanceOrder:
    return FreelanceOrder(
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
        delivery_type=delivery_type,
        delivery_config=order_data.delivery_config,
        delivery_status="pending",
        started_at=datetime.now(timezone.utc),
        user_id=user_uuid,
    )


def _finalize_created_order(
    db: Session,
    order: FreelanceOrder,
    *,
    order_data: FreelanceOrderCreate,
    user_id: str | None,
) -> None:
    if order_data.auto_generate_delivery:
        queue_delivery_generation(db, order.id, user_id=user_id)

    try:
        if is_pipeline_active():
            raise RuntimeError("pipeline_active_memory_capture_disabled")
        queue_memory_capture(
            db=db,
            user_id=user_id,
            agent_namespace="freelance",
            event_type="freelance_order",
            content=f"New Freelance Order: {order.service_type} for {order.client_name}",
            source="freelance_service",
            tags=["freelance", "order", order.service_type],
            node_type="outcome",
            extra={"client_email": order.client_email, "price": order.price},
        )
    except Exception as bridge_err:
        if str(bridge_err) != "pipeline_active_memory_capture_disabled":
            logger.warning("[MemoryBridge] Failed to log freelance order: %s", bridge_err)


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
        operation=lambda: chat_completion(
            get_openai_client(),
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
            timeout=settings.OPENAI_CHAT_TIMEOUT_SECONDS,
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
    orders = q.order_by(FreelanceOrder.created_at.desc()).all()
    for order in orders:
        _apply_subscription_access_control(order)
    return orders


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
        if order.delivery_type == "payment":
            plid = (result or {}).get("payment_link_id")
            if plid and not order.stripe_payment_link_id:
                order.stripe_payment_link_id = plid
        if order.delivery_type == "subscription":
            sub_id = (result or {}).get("subscription_id")
            cust_id = (result or {}).get("customer_id")
            sub_status = (result or {}).get("subscription_status")
            period_end_ts = (result or {}).get("current_period_end")
            if sub_id:
                order.stripe_subscription_id = sub_id
            if cust_id:
                order.stripe_customer_id = cust_id
            if sub_status:
                order.subscription_status = sub_status
            if period_end_ts:
                order.subscription_period_end = datetime.fromtimestamp(
                    int(period_end_ts), tz=timezone.utc
                )
        order.external_response = result
        order.delivery_status = str(result.get("status") or "success")
        order.status = "delivered" if order.delivery_status in {"success", "completed", "manual"} else "delivery_failed"
        order.delivered_at = datetime.now(timezone.utc)
        order.time_to_completion_seconds = _calculate_time_to_completion(order)
        order.income_efficiency = _calculate_income_efficiency(order)
        db.commit()
        db.refresh(order)
        if order.delivery_type == "subscription" and order.stripe_subscription_id:
            queue_system_event(
                db=db,
                event_type=SystemEventTypes.FREELANCE_SUBSCRIPTION_CREATED,
                user_id=order.user_id,
                trace_id=f"stripe-subscription-created-{order.id}",
                source="freelance",
                payload={
                    "order_id": order.id,
                    "subscription_id": order.stripe_subscription_id,
                    "customer_id": order.stripe_customer_id,
                    "subscription_status": order.subscription_status,
                },
                required=True,
            )
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
    from apps.automation.public import execute_automation_action

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
    elif delivery_type == "subscription":
        automation_type = "subscription"
    elif delivery_type not in {"email", "webhook", "stripe"}:
        raise ValueError(f"unsupported_delivery_type:{delivery_type}")

    config.setdefault("content", order.ai_output)
    config.setdefault("body", order.ai_output)
    config.setdefault("recipient", order.client_email)
    config.setdefault("customer_email", order.client_email)
    config.setdefault("product_name", order.service_type or "Freelance Service")
    config.setdefault("price", order.price)
    config.setdefault(
        "metadata",
        {
            "order_id": order.id,
            "service_type": order.service_type,
            "price": order.price,
            "client_email": order.client_email,
            "client_name": order.client_name,
        },
    )
    payload = {
        "automation_type": automation_type,
        "automation_config": config,
        "task_name": f"freelance_delivery:{order.service_type}",
        "task_id": order.task_id,
        "masterplan_id": order.masterplan_id,
        "user_id": str(order.user_id) if order.user_id else None,
    }
    return execute_automation_action(payload, db)


def _stripe_api_post(
    path: str,
    form_data: dict,
    *,
    stripe_key: str,
) -> dict:
    """
    POST form-encoded data to the Stripe API.
    Raises RuntimeError on non-2xx response.
    Uses the same urllib pattern as automation_execution_service.py.
    """
    encoded = _parse.urlencode(form_data).encode("utf-8")
    http_req = _req.Request(
        f"https://api.stripe.com{path}",
        data=encoded,
        headers={
            "Authorization": f"Bearer {stripe_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with _req.urlopen(http_req, timeout=15) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            return body
    except Exception as exc:
        raise RuntimeError(f"stripe_api_error:{path}:{exc}") from exc


def _stripe_api_delete(path, *, stripe_key):
    req = _req.Request(
        f"https://api.stripe.com{path}",
        headers={"Authorization": f"Bearer {stripe_key}"},
        method="DELETE",
    )
    with _req.urlopen(req, timeout=15) as resp:
        return _json.loads(resp.read().decode("utf-8"))


def verify_stripe_signature(
    payload_bytes: bytes,
    sig_header: str,
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Verify Stripe-Signature header using HMAC-SHA256.
    """
    try:
        timestamp: int | None = None
        v1_sigs: list[str] = []
        for item in str(sig_header or "").split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key == "t":
                timestamp = int(value)
            elif key == "v1":
                v1_sigs.append(value)
        if not timestamp or not v1_sigs:
            return False
        if abs(_time.time() - timestamp) > tolerance_seconds:
            return False
        signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
        expected = _hmac.new(
            webhook_secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        return any(_hmac.compare_digest(expected, sig) for sig in v1_sigs)
    except Exception:
        return False


def _build_payment_idempotency_key(
    *,
    payment_intent_id: str | None = None,
    payment_link_id: str | None = None,
) -> str | None:
    return payment_intent_id or payment_link_id


def _mark_webhook_event(
    db: Session,
    event: WebhookEvent,
    *,
    status: str,
) -> None:
    event.processing_status = status
    if status == "processed":
        event.processed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)


def process_stripe_webhook(
    db: Session,
    event_type: str,
    event_data: dict,
    *,
    event_id: str | None = None,
) -> dict:
    """
    Process a verified Stripe webhook event.
    """
    webhook_event = None
    if event_id:
        webhook_event, event_created = check_or_create(
            db,
            WebhookEvent,
            event_id,
            lambda: WebhookEvent(
                event_type=event_type,
                payload=event_data,
                processing_status="pending",
            ),
        )
        if not event_created and webhook_event.processing_status == "processed":
            return {"processed": False, "status": "already_processed"}

    object_data = event_data.get("object") or {}

    if event_type == "checkout.session.completed":
        payment_intent_id = object_data.get("payment_intent")
        payment_link_id = object_data.get("payment_link")
        customer_email = object_data.get("customer_details", {}).get("email")
        record_payment(
            db,
            payment_intent_id=payment_intent_id,
            payment_link_id=payment_link_id,
            customer_email=customer_email,
            idempotency_key=_build_payment_idempotency_key(
                payment_intent_id=payment_intent_id,
                payment_link_id=payment_link_id,
            ),
        )
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "payment_confirmed"}

    if event_type == "payment_intent.succeeded":
        payment_intent_id = object_data.get("id")
        record_payment(
            db,
            payment_intent_id=payment_intent_id,
            idempotency_key=_build_payment_idempotency_key(payment_intent_id=payment_intent_id),
        )
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "payment_confirmed"}

    if event_type == "payment_intent.payment_failed":
        payment_intent_id = object_data.get("id")
        _fail_payment(db, payment_intent_id=payment_intent_id)
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "payment_failed"}

    if event_type == "customer.subscription.updated":
        sub_id = object_data.get("id")
        _update_subscription_status(
            db,
            subscription_id=sub_id,
            event_data=object_data,
        )
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "subscription_updated"}

    if event_type == "customer.subscription.deleted":
        sub_id = object_data.get("id")
        _cancel_subscription_from_webhook(db, subscription_id=sub_id)
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "subscription_cancelled"}

    if event_type == "invoice.payment_succeeded":
        sub_id = object_data.get("subscription")
        period_end = (object_data.get("lines", {}) or {}).get("data", [{}])[0].get("period", {}).get("end")
        _renew_subscription(db, subscription_id=sub_id, period_end=period_end)
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "subscription_renewed"}

    if event_type == "invoice.payment_failed":
        sub_id = object_data.get("subscription")
        _subscription_payment_failed(db, subscription_id=sub_id)
        if webhook_event is not None:
            _mark_webhook_event(db, webhook_event, status="processed")
        return {"processed": True, "action": "subscription_payment_failed"}

    if webhook_event is not None:
        _mark_webhook_event(db, webhook_event, status="ignored")
    return {"processed": False}


def record_payment(
    db: Session,
    *,
    payment_intent_id: str | None = None,
    payment_link_id: str | None = None,
    customer_email: str | None = None,
    idempotency_key: str | None = None,
    return_created: bool = False,
) -> FreelanceOrder | tuple[FreelanceOrder | None, bool] | None:
    order = _find_order_by_stripe_ids(
        db,
        payment_intent_id=payment_intent_id,
        payment_link_id=payment_link_id,
        customer_email=customer_email,
    )
    if not order:
        logger.warning(
            "[Stripe] Payment confirmed but no order found payment_intent_id=%s payment_link_id=%s",
            payment_intent_id,
            payment_link_id,
        )
        if return_created:
            return None, False
        return None

    payment_key = idempotency_key or _build_payment_idempotency_key(
        payment_intent_id=payment_intent_id,
        payment_link_id=payment_link_id,
    )
    was_created = True
    if payment_key:
        _, was_created = check_or_create(
            db,
            PaymentRecord,
            payment_key,
            lambda: PaymentRecord(
                order_id=order.id,
                stripe_payment_intent_id=payment_intent_id,
                stripe_payment_link_id=payment_link_id,
                status="pending",
                user_id=order.user_id,
            ),
        )

    if was_created and order.payment_status != "confirmed":
        order.payment_status = "confirmed"
        order.status = "payment_confirmed"
        order.payment_confirmed_at = datetime.now(timezone.utc)
        if payment_intent_id and not order.stripe_payment_intent_id:
            order.stripe_payment_intent_id = payment_intent_id
        if payment_link_id and not order.stripe_payment_link_id:
            order.stripe_payment_link_id = payment_link_id
        db.commit()
        db.refresh(order)
        if payment_key:
            payment_record = db.query(PaymentRecord).filter(PaymentRecord.idempotency_key == payment_key).first()
            if payment_record is not None:
                payment_record.status = "confirmed"
                payment_record.confirmed_at = order.payment_confirmed_at
                payment_record.stripe_payment_intent_id = payment_intent_id or payment_record.stripe_payment_intent_id
                payment_record.stripe_payment_link_id = payment_link_id or payment_record.stripe_payment_link_id
                db.commit()
        queue_system_event(
            db=db,
            event_type=SystemEventTypes.FREELANCE_PAYMENT_CONFIRMED,
            user_id=order.user_id,
            trace_id=f"stripe-payment-{order.id}",
            source="stripe_webhook",
            payload={
                "order_id": order.id,
                "payment_intent_id": payment_intent_id,
                "payment_link_id": payment_link_id,
                "service_type": order.service_type,
            },
            required=True,
        )
        logger.info("[Stripe] Payment confirmed for order #%s", order.id)
    elif was_created and payment_key:
        payment_record = db.query(PaymentRecord).filter(PaymentRecord.idempotency_key == payment_key).first()
        if payment_record is not None:
            payment_record.status = "confirmed"
            payment_record.confirmed_at = order.payment_confirmed_at or datetime.now(timezone.utc)
            payment_record.stripe_payment_intent_id = payment_intent_id or payment_record.stripe_payment_intent_id
            payment_record.stripe_payment_link_id = payment_link_id or payment_record.stripe_payment_link_id
            db.commit()

    if return_created:
        return order, was_created
    return order


def issue_refund(
    db: Session,
    order_id: int,
    *,
    user_id: str,
    reason: str | None = None,
    idempotency_key: str | None = None,
    return_created: bool = False,
) -> FreelanceOrder | tuple[FreelanceOrder, bool]:
    """
    Issue a Stripe refund for a confirmed payment order.
    """
    import uuid as _uuid

    order = (
        db.query(FreelanceOrder)
        .filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == _uuid.UUID(str(user_id)),
        )
        .first()
    )
    if not order:
        raise ValueError(f"Order {order_id} not found")

    if order.delivery_type != "payment":
        raise ValueError(
            f"Order {order_id} delivery_type is '{order.delivery_type}', "
            "not 'payment'. Only payment orders can be refunded."
        )
    if idempotency_key:
        existing_refund = (
            db.query(RefundRecord)
            .filter(RefundRecord.idempotency_key == idempotency_key)
            .first()
        )
        if existing_refund is not None:
            if return_created:
                return order, False
            return order
    if order.payment_status == "refunded":
        raise ValueError(f"Order {order_id} has already been refunded.")
    if order.payment_status != "confirmed":
        raise ValueError(
            f"Order {order_id} payment_status is '{order.payment_status}'. "
            "Refunds can only be issued for confirmed payments."
        )
    if not order.stripe_payment_intent_id:
        raise ValueError(
            f"Order {order_id} has no stripe_payment_intent_id. "
            "The payment may have been confirmed before webhook tracking "
            "was enabled. Contact support to issue a manual refund."
        )

    stripe_key = settings.STRIPE_SECRET_KEY
    if not stripe_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured. Cannot issue refund.")

    refund_record = None
    if idempotency_key:
        refund_record, was_created = check_or_create(
            db,
            RefundRecord,
            idempotency_key,
            lambda: RefundRecord(
                order_id=order.id,
                stripe_payment_intent_id=order.stripe_payment_intent_id,
                reason=reason,
                amount_cents=int(round(float(order.price or 0.0) * 100)) if order.price is not None else None,
                status="pending",
                user_id=order.user_id,
            ),
        )
        if not was_created:
            if return_created:
                return order, False
            return order

    trace_id = f"freelance-refund-{order.id}"
    refund_data: dict[str, str] = {"payment_intent": order.stripe_payment_intent_id}
    if reason:
        refund_data["reason"] = "requested_by_customer"
        refund_data["metadata[reason_text]"] = reason[:500]

    try:
        response = _stripe_api_post(
            "/v1/refunds",
            refund_data,
            stripe_key=stripe_key,
        )
        refund_id = response.get("id") or ""
    except Exception as exc:
        if refund_record is not None:
            refund_record.status = "failed"
            refund_record.processed_at = datetime.now(timezone.utc)
            db.commit()
        queue_system_event(
            db=db,
            event_type=SystemEventTypes.FREELANCE_REFUND_FAILED,
            user_id=order.user_id,
            trace_id=trace_id,
            source="freelance",
            payload={
                "order_id": order.id,
                "error": str(exc),
            },
            required=True,
        )
        raise RuntimeError(f"Stripe refund failed: {exc}") from exc

    order.refund_id = refund_id
    order.refund_reason = reason
    order.refunded_at = datetime.now(timezone.utc)
    order.payment_status = "refunded"
    order.status = "refunded"
    db.commit()
    db.refresh(order)
    if refund_record is not None:
        refund_record.stripe_refund_id = refund_id
        refund_record.status = "succeeded"
        refund_record.processed_at = order.refunded_at
        db.commit()

    queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_REFUND_ISSUED,
        user_id=order.user_id,
        trace_id=trace_id,
        source="freelance",
        payload={
            "order_id": order.id,
            "refund_id": refund_id,
            "payment_intent_id": order.stripe_payment_intent_id,
            "service_type": order.service_type,
            "reason": reason,
        },
        required=True,
    )
    logger.info("[Stripe] Refund issued order #%s refund_id=%s", order.id, refund_id)
    if return_created:
        return order, True
    return order


def cancel_subscription(
    db: Session,
    order_id: int,
    *,
    user_id: str,
    reason: str | None = None,
) -> FreelanceOrder:
    import uuid as _uuid

    order = (
        db.query(FreelanceOrder)
        .filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == _uuid.UUID(str(user_id)),
        )
        .first()
    )
    if not order:
        raise ValueError(f"Order {order_id} not found")
    if order.delivery_type != "subscription":
        raise ValueError(
            f"Order {order_id} delivery_type is '{order.delivery_type}', "
            "not 'subscription'. Only subscription orders can be cancelled."
        )
    if not order.stripe_subscription_id:
        raise ValueError(f"Order {order_id} has no stripe_subscription_id.")
    if order.subscription_status == "cancelled":
        raise ValueError(f"Order {order_id} subscription is already cancelled.")

    stripe_key = settings.STRIPE_SECRET_KEY
    if not stripe_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured. Cannot cancel subscription.")

    response = _stripe_api_delete(
        f"/v1/subscriptions/{order.stripe_subscription_id}",
        stripe_key=stripe_key,
    )
    order.subscription_status = "cancelled"
    order.status = "subscription_cancelled"
    order.refund_reason = reason or order.refund_reason
    db.commit()
    db.refresh(order)
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_SUBSCRIPTION_CANCELLED,
        user_id=order.user_id,
        trace_id=f"stripe-subscription-cancel-{order.id}",
        source="freelance",
        payload={
            "order_id": order.id,
            "subscription_id": order.stripe_subscription_id,
            "reason": reason,
            "stripe_response_status": response.get("status"),
        },
        required=True,
    )
    return order


def _find_order_by_stripe_ids(
    db: Session,
    *,
    payment_intent_id: str | None = None,
    payment_link_id: str | None = None,
    customer_email: str | None = None,
) -> FreelanceOrder | None:
    """
    Locate the FreelanceOrder for a Stripe event.
    """
    del customer_email

    if payment_intent_id:
        order = (
            db.query(FreelanceOrder)
            .filter(FreelanceOrder.stripe_payment_intent_id == payment_intent_id)
            .first()
        )
        if order:
            return order
    if payment_link_id:
        order = (
            db.query(FreelanceOrder)
            .filter(FreelanceOrder.stripe_payment_link_id == payment_link_id)
            .first()
        )
        if order:
            return order
        if db.bind is not None and db.bind.dialect.name == "sqlite":
            candidates = (
                db.query(FreelanceOrder)
                .filter(FreelanceOrder.delivery_type == "payment")
                .all()
            )
            for candidate in candidates:
                external = candidate.external_response or {}
                if isinstance(external, dict) and external.get("payment_link_id") == payment_link_id:
                    return candidate
        else:
            order = (
                db.query(FreelanceOrder)
                .filter(FreelanceOrder.delivery_type == "payment")
                .filter(
                    cast(FreelanceOrder.external_response, String).is_not(None)
                )
                .filter(FreelanceOrder.external_response.op("->>")("payment_link_id") == payment_link_id)
                .first()
            )
            if order:
                return order
    return None


def _find_order_by_subscription_id(db, subscription_id):
    if not subscription_id:
        return None
    return (
        db.query(FreelanceOrder)
        .filter(FreelanceOrder.stripe_subscription_id == subscription_id)
        .first()
    )


def _apply_subscription_access_control(order: FreelanceOrder) -> FreelanceOrder:
    """
    The freelance domain has no separate entitlement table yet, so
    subscription-backed deliverables are gated off the persisted order status.
    Inactive subscriptions may still view order metadata, but not the delivered
    content blob itself.
    """
    if str(getattr(order, "delivery_type", "") or "").lower() != "subscription":
        return order
    if str(getattr(order, "subscription_status", "") or "").lower() in _SUBSCRIPTION_ACCESS_ACTIVE:
        return order
    order.ai_output = None
    return order


def _confirm_payment(
    db: Session,
    *,
    payment_intent_id: str | None = None,
    payment_link_id: str | None = None,
    customer_email: str | None = None,
) -> FreelanceOrder | None:
    return record_payment(
        db,
        payment_intent_id=payment_intent_id,
        payment_link_id=payment_link_id,
        customer_email=customer_email,
    )


def _fail_payment(
    db: Session,
    *,
    payment_intent_id: str | None,
) -> FreelanceOrder | None:
    order = _find_order_by_stripe_ids(db, payment_intent_id=payment_intent_id)
    if not order:
        return None
    if order.payment_status in {"confirmed", "refunded"}:
        return order
    order.payment_status = "failed"
    order.status = "payment_failed"
    order.delivery_status = "payment_failed"
    if payment_intent_id and not order.stripe_payment_intent_id:
        order.stripe_payment_intent_id = payment_intent_id
    db.commit()
    db.refresh(order)
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_PAYMENT_FAILED,
        user_id=order.user_id,
        trace_id=f"stripe-payment-failed-{order.id}",
        source="stripe_webhook",
        payload={
            "order_id": order.id,
            "payment_intent_id": payment_intent_id,
        },
        required=True,
    )
    logger.warning("[Stripe] Payment failed for order #%s", order.id)
    return order


def _update_subscription_status(db, *, subscription_id, event_data):
    order = _find_order_by_subscription_id(db, subscription_id)
    if not order:
        return
    new_status = event_data.get("status")
    period_end = event_data.get("current_period_end")
    if new_status:
        order.subscription_status = new_status
    if period_end:
        order.subscription_period_end = datetime.fromtimestamp(
            int(period_end), tz=timezone.utc
        )
    db.commit()


def _cancel_subscription_from_webhook(db, *, subscription_id):
    order = _find_order_by_subscription_id(db, subscription_id)
    if not order:
        return
    order.subscription_status = "cancelled"
    order.status = "subscription_cancelled"
    db.commit()
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_SUBSCRIPTION_CANCELLED,
        user_id=order.user_id,
        trace_id=f"stripe-sub-cancelled-{order.id}",
        source="stripe_webhook",
        payload={"order_id": order.id, "subscription_id": subscription_id},
        required=True,
    )


def _renew_subscription(db, *, subscription_id, period_end):
    order = _find_order_by_subscription_id(db, subscription_id)
    if not order:
        return
    order.subscription_status = "active"
    if period_end:
        order.subscription_period_end = datetime.fromtimestamp(
            int(period_end), tz=timezone.utc
        )
    db.commit()
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_SUBSCRIPTION_RENEWED,
        user_id=order.user_id,
        trace_id=f"stripe-sub-renewed-{order.id}",
        source="stripe_webhook",
        payload={"order_id": order.id, "subscription_id": subscription_id},
        required=True,
    )


def _subscription_payment_failed(db, *, subscription_id):
    order = _find_order_by_subscription_id(db, subscription_id)
    if not order:
        return
    order.subscription_status = "past_due"
    db.commit()
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.FREELANCE_SUBSCRIPTION_PAYMENT_FAILED,
        user_id=order.user_id,
        trace_id=f"stripe-sub-failed-{order.id}",
        source="stripe_webhook",
        payload={"order_id": order.id, "subscription_id": subscription_id},
        required=True,
    )


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
        from apps.tasks.public import get_task_by_id, update_task_status
        task = get_task_by_id(db, order.task_id, str(order.user_id))
        if not task:
            return
        if outcome == "success" and task.get("status") != "completed":
            update_task_status(
                db,
                task_id=order.task_id,
                user_id=str(order.user_id),
                status="completed",
            )
        elif outcome == "failure" and task.get("status") == "completed":
            update_task_status(
                db,
                task_id=order.task_id,
                user_id=str(order.user_id),
                status="paused",
            )
    except Exception as exc:
        db.rollback()
        logger.warning("Freelance task feedback sync failed: %s", exc)


def _sync_freelance_automation(db: Session, order: FreelanceOrder) -> None:
    try:
        if not order.task_id or not order.user_id:
            return
        from apps.tasks.public import get_task_by_id, queue_task_automation_by_id
        task = get_task_by_id(db, order.task_id, str(order.user_id))
        if not task or not task.get("automation_type"):
            return
        dispatch = queue_task_automation_by_id(
            db=db,
            task_id=order.task_id,
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




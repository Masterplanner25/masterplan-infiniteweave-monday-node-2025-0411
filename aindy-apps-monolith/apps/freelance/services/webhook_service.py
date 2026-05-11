"""Stripe event -> freelance business outcome dispatch."""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

_SUBSCRIPTION_ACCESS_ACTIVE = {"active", "trialing"}


def handle_stripe_event(db, event: dict) -> str:
    event_type = str(event.get("type") or "")
    data = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(db, data)
    if event_type == "payment_intent.succeeded":
        return _handle_payment_succeeded(db, data)
    if event_type == "payment_intent.payment_failed":
        return _handle_payment_failed(db, data)
    if event_type == "customer.subscription.created":
        return _handle_subscription_created(db, data)
    if event_type == "customer.subscription.updated":
        return _handle_subscription_updated(db, data)
    if event_type == "customer.subscription.deleted":
        return _handle_subscription_cancelled(db, data)
    if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
        return _handle_invoice_paid(db, data)
    if event_type == "invoice.payment_failed":
        return _handle_invoice_payment_failed(db, data)

    logger.info("[stripe] Unhandled event type: %s", event_type)
    return "unhandled"


def _handle_checkout_completed(db, checkout_session: dict) -> str:
    from apps.freelance.services.freelance_service import record_payment

    payment_intent_id = checkout_session.get("payment_intent")
    payment_link_id = checkout_session.get("payment_link")
    customer_email = ((checkout_session.get("customer_details") or {}).get("email"))
    order, was_created = record_payment(
        db,
        payment_intent_id=payment_intent_id,
        payment_link_id=payment_link_id,
        customer_email=customer_email,
        return_created=True,
    )
    if order is None:
        return "no_order_found"
    if was_created:
        _complete_linked_task_via_syscall(db, order, trace_id=f"stripe-payment-{order.id}")
    return "payment_confirmed"


def _handle_payment_succeeded(db, payment_intent: dict) -> str:
    from apps.freelance.services.freelance_service import record_payment

    payment_intent_id = payment_intent.get("id")
    metadata = payment_intent.get("metadata") or {}
    customer_email = (
        metadata.get("customer_email")
        or ((payment_intent.get("charges") or {}).get("data") or [{}])[0].get("billing_details", {}).get("email")
    )
    order, was_created = record_payment(
        db,
        payment_intent_id=payment_intent_id,
        customer_email=customer_email,
        return_created=True,
    )
    if order is None:
        return "no_order_found"
    if was_created:
        _complete_linked_task_via_syscall(db, order, trace_id=f"stripe-payment-{order.id}")
    return "payment_confirmed"


def _handle_payment_failed(db, payment_intent: dict) -> str:
    from apps.freelance.services.freelance_service import _fail_payment

    _fail_payment(db, payment_intent_id=payment_intent.get("id"))
    return "payment_failed"


def _handle_subscription_created(db, subscription: dict) -> str:
    return _handle_subscription_updated(db, subscription)


def _handle_subscription_updated(db, subscription: dict) -> str:
    from apps.freelance.services.freelance_service import (
        _find_order_by_subscription_id,
        _update_subscription_status,
    )

    subscription_id = subscription.get("id")
    _update_subscription_status(db, subscription_id=subscription_id, event_data=subscription)
    order = _find_order_by_subscription_id(db, subscription_id)
    if order is not None:
        _apply_subscription_access_state(db, order)
    return "subscription_updated"


def _handle_subscription_cancelled(db, subscription: dict) -> str:
    from apps.freelance.services.freelance_service import (
        _cancel_subscription_from_webhook,
        _find_order_by_subscription_id,
    )

    subscription_id = subscription.get("id")
    _cancel_subscription_from_webhook(db, subscription_id=subscription_id)
    order = _find_order_by_subscription_id(db, subscription_id)
    if order is not None:
        _apply_subscription_access_state(db, order)
    return "subscription_cancelled"


def _handle_invoice_paid(db, invoice: dict) -> str:
    from apps.freelance.services.freelance_service import (
        _find_order_by_subscription_id,
        _renew_subscription,
    )

    subscription_id = invoice.get("subscription")
    period_end = ((invoice.get("lines") or {}).get("data") or [{}])[0].get("period", {}).get("end")
    _renew_subscription(db, subscription_id=subscription_id, period_end=period_end)
    order = _find_order_by_subscription_id(db, subscription_id)
    if order is not None:
        _apply_subscription_access_state(db, order)
    return "subscription_renewed"


def _handle_invoice_payment_failed(db, invoice: dict) -> str:
    from apps.freelance.services.freelance_service import (
        _find_order_by_subscription_id,
        _subscription_payment_failed,
    )

    subscription_id = invoice.get("subscription")
    _subscription_payment_failed(db, subscription_id=subscription_id)
    order = _find_order_by_subscription_id(db, subscription_id)
    if order is not None:
        _apply_subscription_access_state(db, order)
    return "subscription_payment_failed"


def _apply_subscription_access_state(db, order) -> None:
    status = str(getattr(order, "subscription_status", "") or "").lower()
    if status in _SUBSCRIPTION_ACCESS_ACTIVE:
        order.status = "subscription_active"
    elif status in {"cancelled", "canceled"}:
        order.status = "subscription_cancelled"
    elif status:
        order.status = "subscription_restricted"
    db.commit()


def _complete_linked_task_via_syscall(db, order, *, trace_id: str) -> None:
    try:
        if not getattr(order, "task_id", None) or not getattr(order, "user_id", None):
            return

        from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

        ctx = SyscallContext(
            execution_unit_id=str(uuid.uuid4()),
            user_id=str(order.user_id),
            capabilities=["task.read", "task.complete"],
            trace_id=trace_id,
            metadata={"_db": db},
        )
        task_result = get_dispatcher().dispatch(
            "sys.v1.task.get",
            {"task_id": int(order.task_id), "user_id": str(order.user_id)},
            ctx,
        )
        if task_result.get("status") != "success":
            return
        task = ((task_result.get("data") or {}).get("task") or {})
        task_name = task.get("name")
        if str(task.get("status") or "").lower() == "completed":
            return
        if not task_name:
            return
        get_dispatcher().dispatch(
            "sys.v1.task.complete",
            {"task_name": task_name},
            ctx,
        )
    except Exception as exc:
        logger.warning("[stripe] linked task completion failed (non-fatal): %s", exc)

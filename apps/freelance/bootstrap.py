"""Freelance domain bootstrap."""
from __future__ import annotations

import logging

BOOTSTRAP_DEPENDS_ON: list[str] = ["automation"]
APP_DEPENDS_ON: list[str] = ["automation", "search", "tasks"]

logger = logging.getLogger(__name__)


def register() -> None:
    _register_models()
    _register_router()
    _register_events()
    _register_jobs()
    _register_async_jobs()
    _register_flows()
    _register_flow_results()
    _register_health_check()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.freelance.models as freelance_models

    register_models(freelance_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(freelance_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_router() -> None:
    from AINDY.config import settings
    from AINDY.platform_layer.registry import register_router
    from apps.freelance.routes.freelance_router import router as freelance_router

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning(
            "[freelance] STRIPE_WEBHOOK_SECRET is not set. "
            "Stripe webhooks will reject all incoming events with 400. "
            "Set STRIPE_WEBHOOK_SECRET to enable payment automation."
        )
    register_router(freelance_router)


def _register_events() -> None:
    from AINDY.platform_layer.registry import register_event_type
    from apps.freelance.events import FreelanceEventTypes

    for value in vars(FreelanceEventTypes).values():
        if isinstance(value, str):
            register_event_type(value)


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job
    register_job("freelance.generate_delivery", _freelance_generate_delivery)


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job
    register_async_job("freelance.generate_delivery")(_job_freelance_generate_delivery)


def _register_flows() -> None:
    from AINDY.platform_layer.registry import register_flow, register_symbols
    from apps.freelance.flows import freelance_flows

    register_symbols(
        {
            name: value
            for name, value in vars(freelance_flows).items()
            if not name.startswith("__")
        }
    )
    register_flow(freelance_flows.register)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "freelance_order_create": "freelance_order_create_result",
        "freelance_order_deliver": "freelance_order_deliver_result",
        "freelance_delivery_update": "freelance_delivery_update_result",
        "freelance_feedback_collect": "freelance_feedback_collect_result",
        "freelance_orders_list": "freelance_orders_list_result",
        "freelance_feedback_list": "freelance_feedback_list_result",
        "freelance_metrics_latest": "freelance_metrics_latest_result",
        "freelance_metrics_update": "freelance_metrics_update_result",
        "freelance_delivery_generate": "freelance_delivery_generate_result",
        "freelance_refund": "freelance_refund_result",
        "freelance_subscription_cancel": "freelance_subscription_cancel_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)


def _freelance_generate_delivery(*, db, order_id, user_id=None):
    from apps.freelance.services.freelance_service import generate_deliverable
    return generate_deliverable(db=db, order_id=order_id, user_id=user_id)


def _job_freelance_generate_delivery(payload: dict, db):
    return _freelance_generate_delivery(
        db=db,
        order_id=int(payload["order_id"]),
        user_id=payload.get("user_id"),
    )


def freelance_health_check() -> bool:
    from AINDY.config import settings
    from AINDY.db.database import SessionLocal

    if not settings.STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY not configured - payment orders will fail")

    try:
        from apps.freelance.models import FreelanceOrder
    except Exception as exc:
        raise RuntimeError(f"freelance health import failed: {exc}") from exc

    db = SessionLocal()
    try:
        db.query(FreelanceOrder.id).limit(1).all()
        return True
    finally:
        db.close()


def _register_health_check() -> None:
    from AINDY.platform_layer.domain_health import domain_health_registry
    from AINDY.platform_layer.registry import register_health_check

    domain_health_registry.register("freelance", freelance_health_check)
    register_health_check("freelance", _check_health)


def _check_health() -> dict:
    db = None
    reasons: list[str] = []
    try:
        from AINDY.config import settings
        from AINDY.db.database import SessionLocal
        from apps.freelance.models import FreelanceOrder

        db = SessionLocal()
        db.query(FreelanceOrder.id).limit(1).all()
        if not settings.STRIPE_SECRET_KEY:
            reasons.append("stripe key not configured")
        if reasons:
            return {"status": "degraded", "reason": "; ".join(reasons)}
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}
    finally:
        if db is not None:
            db.close()

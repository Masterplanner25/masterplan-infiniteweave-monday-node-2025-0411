"""Freelance domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_models()
    _register_router()
    _register_events()
    _register_jobs()
    _register_async_jobs()
    _register_flow_results()


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
    from AINDY.platform_layer.registry import register_router
    from apps.freelance.routes.freelance_router import router as freelance_router
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

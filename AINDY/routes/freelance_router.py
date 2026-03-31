from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from db.models.freelance import FreelanceOrder
from schemas.freelance import (
    FeedbackCreate,
    FeedbackResponse,
    FreelanceDeliveryConfigUpdate,
    FreelanceOrderCreate,
    FreelanceOrderResponse,
    RevenueMetricsResponse,
)
from services import freelance_service
from services.auth_service import get_current_user
from services.execution_service import ExecutionContext, ExecutionErrorConfig, run_execution

router = APIRouter(prefix="/freelance", tags=["Freelance"], dependencies=[Depends(get_current_user)])


def _execute_freelance(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None, success_status_code: int = 200):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload,
        metadata={"db": db, "source": "freelance"},
        success_status_code=success_status_code,
    )


def _serialize_order(order) -> dict:
    return FreelanceOrderResponse.model_validate(order).model_dump(mode="json")


def _serialize_feedback(feedback) -> dict:
    return FeedbackResponse.model_validate(feedback).model_dump(mode="json")


def _serialize_metric(metric) -> dict:
    return RevenueMetricsResponse.model_validate(metric).model_dump(mode="json")


@router.post("/order", status_code=201)
def create_freelance_order(
    request: Request,
    order: FreelanceOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
            ExecutionContext(
                db=db,
                user_id=user_id,
                source="freelance",
                operation="freelance.order.create",
                start_payload={"service_type": order.service_type, "client_name": order.client_name},
            ),
            lambda: {
                "data": _serialize_order(freelance_service.create_order(db, order, user_id=user_id)),
                "execution_signals": {
                    "memory": {
                        "event_type": "freelance_order",
                        "content": f"New Freelance Order: {order.service_type} for {order.client_name}",
                        "source": "freelance_service",
                        "tags": ["freelance", "order", order.service_type],
                        "node_type": "outcome",
                        "user_id": user_id,
                        "agent_namespace": "freelance",
                        "extra": {"client_email": order.client_email, "price": order.price},
                    }
                }
            },
            success_status_code=201,
            completed_payload_builder=lambda created: {"order_id": created["data"]["id"]},
            handled_exceptions={
                Exception: ExecutionErrorConfig(status_code=500, message="Failed to create order"),
            },
        )
    return _execute_freelance(request, "freelance.order.create", handler, db=db, user_id=user_id, input_payload={"service_type": order.service_type, "client_name": order.client_name}, success_status_code=201)


@router.post("/deliver/{order_id}")
def deliver_order(
    request: Request,
    order_id: int,
    ai_output: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.order.deliver",
            start_payload={"order_id": order_id},
        ),
        lambda: {
            "data": _serialize_order(_require_owned_order_delivery(db, user_id, order_id, ai_output)),
            "execution_signals": {
                "memory": {
                    "event_type": "freelance_delivery",
                    "content": f"Delivered Order #{order_id}",
                    "source": "freelance_service",
                    "tags": ["freelance", "delivery"],
                    "node_type": "outcome",
                    "user_id": user_id,
                    "agent_namespace": "freelance",
                }
            },
        },
        completed_payload_builder=lambda delivered: {"order_id": delivered["data"]["id"]},
        handled_exceptions={
            LookupError: ExecutionErrorConfig(status_code=404, message="Order not found"),
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to deliver order"),
        },
    )
    return _execute_freelance(request, "freelance.order.deliver", handler, db=db, user_id=user_id, input_payload={"order_id": order_id})


@router.put("/delivery/{order_id}")
def update_delivery_configuration(
    request: Request,
    order_id: int,
    body: FreelanceDeliveryConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.delivery.update",
            start_payload={"order_id": order_id, "delivery_type": body.delivery_type},
        ),
        lambda: _serialize_order(
            freelance_service.update_delivery_config(
                db=db,
                order_id=order_id,
                user_id=user_id,
                delivery_type=body.delivery_type,
                delivery_config=body.delivery_config,
            )
        ),
        completed_payload_builder=lambda updated: {"order_id": updated["id"]},
        handled_exceptions={
            ValueError: ExecutionErrorConfig(status_code=404, message="Order not found"),
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to update delivery configuration"),
        },
    )
    return _execute_freelance(request, "freelance.delivery.update", handler, db=db, user_id=user_id, input_payload={"order_id": order_id, "delivery_type": body.delivery_type})


@router.post("/feedback")
def collect_feedback(
    request: Request,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.feedback.collect",
            start_payload={"order_id": feedback.order_id},
        ),
        lambda: {
            "data": _serialize_feedback(freelance_service.collect_feedback(db, feedback, user_id=user_id)),
            "execution_signals": {
                "memory": {
                    "event_type": "freelance_feedback",
                    "content": f"Feedback for Order #{feedback.order_id}",
                    "source": "freelance_service",
                    "tags": ["freelance", "feedback"],
                    "node_type": "insight",
                    "user_id": user_id,
                    "agent_namespace": "freelance",
                    "extra": {"rating": feedback.rating},
                }
            },
        },
        completed_payload_builder=lambda collected: {"order_id": collected["data"]["order_id"]},
        handled_exceptions={
            ValueError: ExecutionErrorConfig(status_code=404, message="Feedback target not found"),
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to collect feedback"),
        },
    )
    return _execute_freelance(request, "freelance.feedback.collect", handler, db=db, user_id=user_id, input_payload={"order_id": feedback.order_id})


@router.get("/orders")
def get_all_orders(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
            ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.orders.list"),
            lambda: [_serialize_order(order) for order in freelance_service.get_all_orders(db, user_id=user_id)],
            completed_payload_builder=lambda orders: {"count": len(orders)},
        )
    return _execute_freelance(request, "freelance.orders.list", handler, db=db, user_id=user_id)


@router.get("/feedback")
def get_all_feedback(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
            ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.feedback.list"),
            lambda: [_serialize_feedback(item) for item in freelance_service.get_all_feedback(db, user_id=user_id)],
            completed_payload_builder=lambda feedback_items: {"count": len(feedback_items)},
        )
    return _execute_freelance(request, "freelance.feedback.list", handler, db=db, user_id=user_id)


@router.get("/metrics/latest")
def get_latest_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
            ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.metrics.latest"),
            lambda: _serialize_metric(_require_latest_metric(db)),
            handled_exceptions={
                LookupError: ExecutionErrorConfig(status_code=404, message="No revenue metrics found"),
            },
        )
    return _execute_freelance(request, "freelance.metrics.latest", handler, db=db, user_id=user_id)


@router.post("/metrics/update")
def update_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
            ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.metrics.update"),
            lambda: _serialize_metric(freelance_service.update_revenue_metrics(db, user_id=user_id)),
            handled_exceptions={
                Exception: ExecutionErrorConfig(status_code=500, message="Metrics update failed"),
            },
        )
    return _execute_freelance(request, "freelance.metrics.update", handler, db=db, user_id=user_id)


@router.post("/generate/{order_id}")
def generate_delivery(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.delivery.generate",
            start_payload={"order_id": order_id},
        ),
        lambda: _require_owned_order_generation(db, user_id, order_id),
        completed_payload_builder=lambda dispatch: {"order_id": order_id, "automation_log_id": dispatch.get("automation_log_id")},
        handled_exceptions={
            LookupError: ExecutionErrorConfig(status_code=404, message="Order not found"),
            ValueError: ExecutionErrorConfig(status_code=404, message="Order not found"),
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to queue freelance delivery generation"),
        },
    )
    return _execute_freelance(request, "freelance.delivery.generate", handler, db=db, user_id=user_id, input_payload={"order_id": order_id})


def _owned_order(db: Session, user_id: str, order_id: int):
    return (
        db.query(FreelanceOrder)
        .filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == uuid.UUID(user_id),
        )
        .first()
    )


def _require_owned_order_delivery(db: Session, user_id: str, order_id: int, ai_output: str | None):
    order = _owned_order(db, user_id, order_id)
    if not order:
        raise LookupError(order_id)
    return freelance_service.deliver_order(db, order_id, ai_output, generated_by_ai=False)


def _require_latest_metric(db: Session):
    metric = freelance_service.get_latest_metrics(db)
    if not metric:
        raise LookupError("latest_metric")
    return metric


def _require_owned_order_generation(db: Session, user_id: str, order_id: int):
    order = _owned_order(db, user_id, order_id)
    if not order:
        raise LookupError(order_id)
    return freelance_service.queue_delivery_generation(db, order_id=order_id, user_id=user_id)

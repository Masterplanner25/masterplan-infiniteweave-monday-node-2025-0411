from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

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


def _serialize_order(order) -> dict:
    return FreelanceOrderResponse.model_validate(order).model_dump(mode="json")


def _serialize_feedback(feedback) -> dict:
    return FeedbackResponse.model_validate(feedback).model_dump(mode="json")


def _serialize_metric(metric) -> dict:
    return RevenueMetricsResponse.model_validate(metric).model_dump(mode="json")


@router.post("/order", status_code=201)
def create_freelance_order(
    order: FreelanceOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.order.create",
            start_payload={"service_type": order.service_type, "client_name": order.client_name},
        ),
        lambda: _serialize_order(freelance_service.create_order(db, order, user_id=user_id)),
        success_status_code=201,
        completed_payload_builder=lambda created: {"order_id": created["id"]},
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to create order"),
        },
    )


@router.post("/deliver/{order_id}")
def deliver_order(
    order_id: int,
    ai_output: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.order.deliver",
            start_payload={"order_id": order_id},
        ),
        lambda: _serialize_order(_require_owned_order_delivery(db, user_id, order_id, ai_output)),
        completed_payload_builder=lambda delivered: {"order_id": delivered["id"]},
        handled_exceptions={
            LookupError: ExecutionErrorConfig(status_code=404, message="Order not found"),
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to deliver order"),
        },
    )


@router.put("/delivery/{order_id}")
def update_delivery_configuration(
    order_id: int,
    body: FreelanceDeliveryConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
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


@router.post("/feedback")
def collect_feedback(
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.feedback.collect",
            start_payload={"order_id": feedback.order_id},
        ),
        lambda: _serialize_feedback(freelance_service.collect_feedback(db, feedback, user_id=user_id)),
        completed_payload_builder=lambda collected: {"order_id": collected["order_id"]},
        handled_exceptions={
            ValueError: ExecutionErrorConfig(status_code=404, message="Feedback target not found"),
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to collect feedback"),
        },
    )


@router.get("/orders")
def get_all_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.orders.list"),
        lambda: [_serialize_order(order) for order in freelance_service.get_all_orders(db, user_id=user_id)],
        completed_payload_builder=lambda orders: {"count": len(orders)},
    )


@router.get("/feedback")
def get_all_feedback(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.feedback.list"),
        lambda: [_serialize_feedback(item) for item in freelance_service.get_all_feedback(db, user_id=user_id)],
        completed_payload_builder=lambda feedback_items: {"count": len(feedback_items)},
    )


@router.get("/metrics/latest")
def get_latest_metrics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.metrics.latest"),
        lambda: _serialize_metric(_require_latest_metric(db)),
        handled_exceptions={
            LookupError: ExecutionErrorConfig(status_code=404, message="No revenue metrics found"),
        },
    )


@router.post("/metrics/update")
def update_metrics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="freelance", operation="freelance.metrics.update"),
        lambda: _serialize_metric(freelance_service.update_revenue_metrics(db, user_id=user_id)),
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Metrics update failed"),
        },
    )


@router.post("/generate/{order_id}")
def generate_delivery(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
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

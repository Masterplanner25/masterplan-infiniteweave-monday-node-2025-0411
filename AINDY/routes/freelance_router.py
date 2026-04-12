from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_service import ExecutionContext
from AINDY.core.execution_service import run_execution
from AINDY.db.database import get_db
from AINDY.schemas.freelance import (
    FeedbackCreate,
    FreelanceDeliveryConfigUpdate,
    FreelanceOrderCreate,
)
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/freelance", tags=["Freelance"], dependencies=[Depends(get_current_user)])


def _run_flow_freelance(flow_name: str, payload: dict, db: Session, user_id: str, *, return_full: bool = False):
    from AINDY.runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    return result if return_full else result.get("data")


def _execute_freelance(request: Request, route_name: str, handler, *, db: Session, user_id: str,
                       input_payload=None, success_status_code: int = 200):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation=route_name,
            start_payload=input_payload or {},
        ),
        lambda: handler(None),
        success_status_code=success_status_code,
    )


@router.post("/order", status_code=201)
def create_freelance_order(
    request: Request,
    order: FreelanceOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        result = _run_flow_freelance("freelance_order_create", {"order": order.model_dump()}, db, user_id)
        return result.get("data") if isinstance(result, dict) and "data" in result else result
    return _execute_freelance(request, "freelance.order.create", handler, db=db, user_id=user_id,
                              input_payload={"service_type": order.service_type, "client_name": order.client_name},
                              success_status_code=201)


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
        result = _run_flow_freelance("freelance_order_deliver", {"order_id": order_id, "ai_output": ai_output}, db, user_id)
        return result.get("data") if isinstance(result, dict) and "data" in result else result
    return _execute_freelance(request, "freelance.order.deliver", handler, db=db, user_id=user_id,
                              input_payload={"order_id": order_id})


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
        return _run_flow_freelance(
            "freelance_delivery_update",
            {"order_id": order_id, "delivery_type": body.delivery_type, "delivery_config": body.delivery_config},
            db, user_id,
        )
    return _execute_freelance(request, "freelance.delivery.update", handler, db=db, user_id=user_id,
                              input_payload={"order_id": order_id, "delivery_type": body.delivery_type})


@router.post("/feedback")
def collect_feedback(
    request: Request,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        result = _run_flow_freelance("freelance_feedback_collect", {"feedback": feedback.model_dump()}, db, user_id)
        return result.get("data") if isinstance(result, dict) and "data" in result else result
    return _execute_freelance(request, "freelance.feedback.collect", handler, db=db, user_id=user_id,
                              input_payload={"order_id": feedback.order_id})


@router.get("/orders")
def get_all_orders(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        result = _run_flow_freelance("freelance_orders_list", {}, db, user_id, return_full=True)
        data = result.get("data") or {}
        return {
            "status": result.get("status"),
            "orders": data.get("orders", []),
        }
    return _execute_freelance(request, "freelance.orders.list", handler, db=db, user_id=user_id)


@router.get("/feedback")
def get_all_feedback(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_freelance("freelance_feedback_list", {}, db, user_id)
    return _execute_freelance(request, "freelance.feedback.list", handler, db=db, user_id=user_id)


@router.get("/metrics/latest")
def get_latest_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_freelance("freelance_metrics_latest", {}, db, user_id)
    return _execute_freelance(request, "freelance.metrics.latest", handler, db=db, user_id=user_id)


@router.post("/metrics/update")
def update_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_freelance("freelance_metrics_update", {}, db, user_id)
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
        return _run_flow_freelance("freelance_delivery_generate", {"order_id": order_id}, db, user_id)
    return _execute_freelance(request, "freelance.delivery.generate", handler, db=db, user_id=user_id,
                              input_payload={"order_id": order_id})


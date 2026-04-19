import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.core.execution_service import ExecutionContext, run_execution
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from apps.freelance.schemas.freelance import (
    FeedbackCreate,
    FreelanceDeliveryConfigUpdate,
    FreelanceOrderCreate,
)
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/freelance", tags=["Freelance"], dependencies=[Depends(get_current_user)])


def _unwrap_execution_response(response):
    if isinstance(response, dict):
        payload = response.get("data")
        if (
            response.get("status") == "SUCCESS"
            and isinstance(payload, dict)
            and "trace_id" in response
        ):
            return payload
        return response

    if isinstance(response, JSONResponse):
        payload = json.loads(response.body.decode("utf-8"))
        if (
            isinstance(payload, dict)
            and payload.get("status") == "SUCCESS"
            and isinstance(payload.get("data"), dict)
            and "trace_id" in payload
        ):
            return JSONResponse(
                status_code=response.status_code,
                content=payload["data"],
                headers=dict(response.headers),
            )
    return response


def _run_freelance_execution(
    context: ExecutionContext,
    fn,
    *,
    success_status_code: int = 200,
):
    return _unwrap_execution_response(
        run_execution(
            context,
            fn,
            success_status_code=success_status_code,
        )
    )


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
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata={"db": db, "source": "freelance"},
        success_status_code=success_status_code,
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    data = result.data
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault(
            "execution_envelope",
            to_envelope(
                eu_id=result.metadata.get("eu_id"),
                trace_id=result.metadata.get("trace_id"),
                status="SUCCESS",
                output=None,
                error=None,
                duration_ms=None,
                attempt_count=1,
            ),
        )
    return data


def _do_create_freelance_order(db: Session, order: FreelanceOrderCreate, user_id: str):
    result = _run_flow_freelance("freelance_order_create", {"order": order.model_dump()}, db, user_id)
    return result.get("data") if isinstance(result, dict) and "data" in result else result


def _do_deliver_order(db: Session, order_id: int, ai_output: str | None, user_id: str):
    result = _run_flow_freelance(
        "freelance_order_deliver",
        {"order_id": order_id, "ai_output": ai_output},
        db,
        user_id,
    )
    return result.get("data") if isinstance(result, dict) and "data" in result else result


def _do_update_delivery_configuration(
    db: Session,
    order_id: int,
    body: FreelanceDeliveryConfigUpdate,
    user_id: str,
):
    return _run_flow_freelance(
        "freelance_delivery_update",
        {
            "order_id": order_id,
            "delivery_type": body.delivery_type,
            "delivery_config": body.delivery_config,
        },
        db,
        user_id,
    )


def _do_collect_feedback(db: Session, feedback: FeedbackCreate, user_id: str):
    result = _run_flow_freelance("freelance_feedback_collect", {"feedback": feedback.model_dump()}, db, user_id)
    return result.get("data") if isinstance(result, dict) and "data" in result else result


def _do_update_metrics(db: Session, user_id: str):
    return _run_flow_freelance("freelance_metrics_update", {}, db, user_id)


def _do_generate_delivery(db: Session, order_id: int, user_id: str):
    return _run_flow_freelance("freelance_delivery_generate", {"order_id": order_id}, db, user_id)


@router.post("/order", status_code=201)
@limiter.limit("30/minute")
def create_freelance_order(
    request: Request,
    order: FreelanceOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _run_freelance_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.order.create",
            start_payload=order.model_dump(),
        ),
        lambda: _do_create_freelance_order(db, order, user_id),
        success_status_code=201,
    )


@router.post("/deliver/{order_id}")
@limiter.limit("30/minute")
def deliver_order(
    request: Request,
    order_id: int,
    ai_output: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _run_freelance_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.order.deliver",
            start_payload={"order_id": order_id, "ai_output": ai_output},
        ),
        lambda: _do_deliver_order(db, order_id, ai_output, user_id),
    )


@router.put("/delivery/{order_id}")
@limiter.limit("30/minute")
def update_delivery_configuration(
    request: Request,
    order_id: int,
    body: FreelanceDeliveryConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _run_freelance_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.delivery.update",
            start_payload={
                "order_id": order_id,
                "delivery_type": body.delivery_type,
                "delivery_config": body.delivery_config,
            },
        ),
        lambda: _do_update_delivery_configuration(db, order_id, body, user_id),
    )


@router.post("/feedback")
@limiter.limit("30/minute")
def collect_feedback(
    request: Request,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _run_freelance_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.feedback.collect",
            start_payload=feedback.model_dump(),
        ),
        lambda: _do_collect_feedback(db, feedback, user_id),
    )


@router.get("/orders")
@limiter.limit("60/minute")
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
@limiter.limit("60/minute")
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
@limiter.limit("60/minute")
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
@limiter.limit("30/minute")
def update_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _run_freelance_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.metrics.update",
            start_payload={},
        ),
        lambda: _do_update_metrics(db, user_id),
    )


@router.post("/generate/{order_id}")
@limiter.limit("30/minute")
def generate_delivery(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _run_freelance_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="freelance",
            operation="freelance.delivery.generate",
            start_payload={"order_id": order_id},
        ),
        lambda: _do_generate_delivery(db, order_id, user_id),
    )


from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from apps.analytics.schemas.analytics import LinkedInRawInput
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _with_execution_envelope(payload):
    envelope = to_envelope(
        eu_id=None,
        trace_id=None,
        status="SUCCESS",
        output=None,
        error=None,
        duration_ms=None,
        attempt_count=1,
    )
    if hasattr(payload, "status_code") and hasattr(payload, "body"):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        result = dict(data) if isinstance(data, dict) else dict(payload)
        result.setdefault("execution_envelope", envelope)
        return result
    return {"data": payload, "execution_envelope": envelope}


def _analytics_http_error(data):
    """Raise HTTPException if node encoded an HTTP error."""
    if isinstance(data, dict) and "_http_error" in data:
        err = data["_http_error"]
        raise HTTPException(status_code=err["status_code"], detail=err["detail"])


@router.post("/linkedin/manual")
@limiter.limit("30/minute")
async def ingest_linkedin_manual(
    request: Request,
    data: LinkedInRawInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.masterplan_guard import assert_masterplan_owned_via_syscall
        from runtime.flow_engine import run_flow

        assert_masterplan_owned_via_syscall(data.masterplan_id, user_id, db)

        result = run_flow(
            "analytics_linkedin_ingest",
            {"data": data.model_dump()},
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            if error.startswith("HTTP_"):
                parts = error.split(":", 1)
                raise HTTPException(
                    status_code=int(parts[0].replace("HTTP_", "")),
                    detail={"error": "masterplan_not_found", "message": parts[1] if len(parts) > 1 else error},
                )
            raise HTTPException(status_code=500, detail="Analytics ingest failed")
        return result.get("data")

    result = await execute_with_pipeline(
        request=request, route_name="analytics.linkedin.manual", handler=handler,
        user_id=user_id, metadata={"db": db}, input_payload=data.model_dump(),
    )
    return _with_execution_envelope(result)


@router.get("/masterplan/{masterplan_id}")
@limiter.limit("60/minute")
async def get_masterplan_analytics(
    request: Request,
    masterplan_id: int,
    period_type: str | None = None,
    platform: str | None = None,
    scope_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.masterplan_guard import assert_masterplan_owned_via_syscall
        from runtime.flow_engine import run_flow

        assert_masterplan_owned_via_syscall(masterplan_id, user_id, db)

        result = run_flow(
            "analytics_masterplan_get",
            {"masterplan_id": masterplan_id, "period_type": period_type, "platform": platform, "scope_type": scope_type},
            db=db, user_id=user_id,
        )
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            if "404" in error:
                raise HTTPException(status_code=404, detail={"error": "masterplan_not_found", "message": "MasterPlan not found"})
            raise HTTPException(status_code=500, detail="Analytics fetch failed")
        return result.get("data")

    return await execute_with_pipeline(
        request=request, route_name="analytics.masterplan.get", handler=handler,
        user_id=user_id, metadata={"db": db},
    )


@router.get("/masterplan/{masterplan_id}/summary")
@limiter.limit("60/minute")
async def get_masterplan_summary(
    request: Request,
    masterplan_id: int,
    group_by: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.masterplan_guard import assert_masterplan_owned_via_syscall
        from runtime.flow_engine import run_flow

        assert_masterplan_owned_via_syscall(masterplan_id, user_id, db)

        result = run_flow(
            "analytics_masterplan_summary",
            {"masterplan_id": masterplan_id, "group_by": group_by},
            db=db, user_id=user_id,
        )
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            if "404" in error:
                raise HTTPException(status_code=404, detail={"error": "masterplan_not_found", "message": "MasterPlan not found"})
            raise HTTPException(status_code=500, detail="Analytics summary failed")
        return result.get("data")

    return await execute_with_pipeline(
        request=request, route_name="analytics.masterplan.summary", handler=handler,
        user_id=user_id, metadata={"db": db},
    )


@router.get("/kpi-weights")
@limiter.limit("60/minute")
async def get_kpi_weights(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.kpi_weight_service import (
            get_effective_weights,
            get_or_create_user_weights,
        )

        row = get_or_create_user_weights(db, user_id)
        return {
            "weights": get_effective_weights(db, user_id),
            "adapted_count": int(row.adapted_count or 0),
            "last_adapted_at": row.last_adapted_at.isoformat() if row.last_adapted_at else None,
            "is_personalized": bool((row.adapted_count or 0) > 0),
        }

    result = await execute_with_pipeline(
        request=request,
        route_name="analytics.kpi_weights.get",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )
    return _with_execution_envelope(result)


@router.post("/kpi-weights/adapt")
@limiter.limit("5/minute")
async def adapt_kpi_weights_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.kpi_weight_service import adapt_kpi_weights

        return adapt_kpi_weights(db, user_id)

    result = await execute_with_pipeline(
        request=request,
        route_name="analytics.kpi_weights.adapt",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )
    return _with_execution_envelope(result)


@router.get("/policy-thresholds")
@limiter.limit("30/minute")
async def get_policy_thresholds(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.policy_adaptation_service import (
            get_effective_thresholds,
            get_or_create_thresholds,
        )

        result = dict(get_effective_thresholds(db, user_id))
        row = get_or_create_thresholds(db, user_id)
        result["adapted_count"] = int(row.adapted_count or 0)
        result["last_adapted_at"] = row.last_adapted_at.isoformat() if row.last_adapted_at else None
        return result

    result = await execute_with_pipeline(
        request=request,
        route_name="analytics.policy_thresholds.get",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )
    return _with_execution_envelope(result)


@router.post("/policy-thresholds/adapt")
@limiter.limit("5/minute")
async def adapt_policy_thresholds_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.analytics.services.policy_adaptation_service import adapt_policy_thresholds

        return adapt_policy_thresholds(db, user_id)

    result = await execute_with_pipeline(
        request=request,
        route_name="analytics.policy_thresholds.adapt",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )
    return _with_execution_envelope(result)

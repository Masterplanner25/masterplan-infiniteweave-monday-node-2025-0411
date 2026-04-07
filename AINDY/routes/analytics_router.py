from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from core.execution_helper import execute_with_pipeline
from db.database import get_db
from schemas.analytics import LinkedInRawInput
from services.auth_service import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _analytics_http_error(data):
    """Raise HTTPException if node encoded an HTTP error."""
    if isinstance(data, dict) and "_http_error" in data:
        err = data["_http_error"]
        raise HTTPException(status_code=err["status_code"], detail=err["detail"])


@router.post("/linkedin/manual")
async def ingest_linkedin_manual(
    request: Request,
    data: LinkedInRawInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from domain.masterplan_service import assert_masterplan_owned
        from runtime.flow_engine import run_flow

        assert_masterplan_owned(db, data.masterplan_id, user_id)

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

    return await execute_with_pipeline(
        request=request, route_name="analytics.linkedin.manual", handler=handler,
        user_id=user_id, metadata={"db": db}, input_payload=data.model_dump(),
    )


@router.get("/masterplan/{masterplan_id}")
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
        from domain.masterplan_service import assert_masterplan_owned
        from runtime.flow_engine import run_flow

        assert_masterplan_owned(db, masterplan_id, user_id)

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
async def get_masterplan_summary(
    request: Request,
    masterplan_id: int,
    group_by: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from domain.masterplan_service import assert_masterplan_owned
        from runtime.flow_engine import run_flow

        assert_masterplan_owned(db, masterplan_id, user_id)

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

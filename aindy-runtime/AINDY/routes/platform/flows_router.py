from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.nodus_shared import _run_flow_platform
from AINDY.routes.platform.schemas import FlowDefinition, FlowRunRequest
from AINDY.services.auth_service import get_current_user

router = APIRouter()


@router.post("/flows", status_code=201, response_model=None)
@limiter.limit("30/minute")
def create_flow(request: Request, body: FlowDefinition, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.flow_registry import register_dynamic_flow

    user_id = str(current_user["sub"])
    try:
        return register_dynamic_flow(
            name=body.name,
            nodes=body.nodes,
            edges=body.edges,
            start=body.start,
            end=body.end,
            user_id=user_id,
            overwrite=body.overwrite,
            db=db,
        )
    except ValueError as exc:
        errors = exc.args[0]
        raise HTTPException(status_code=422, detail={"errors": errors if isinstance(errors, list) else [str(errors)]})


@router.get("/flows", response_model=None)
@limiter.limit("60/minute")
def list_flows(request: Request, current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.flow_registry import list_dynamic_flows

    return {"flows": list_dynamic_flows()}


@router.get("/flows/{name}", response_model=None)
@limiter.limit("60/minute")
def get_flow(request: Request, name: str, current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.flow_registry import get_dynamic_flow

    meta = get_dynamic_flow(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Flow {name!r} not found")
    return meta


@router.post("/flows/{name}/run", response_model=None)
@limiter.limit("30/minute")
def run_flow_endpoint(request: Request, name: str, body: FlowRunRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.flow_engine import FLOW_REGISTRY

    user_id = str(current_user["sub"])
    if name not in FLOW_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Flow {name!r} is not registered")

    return execute_with_pipeline_sync(
        request=request,
        route_name="platform.flows.run",
        handler=lambda _ctx: _run_flow_platform(name, body.state, db, user_id),
        user_id=user_id,
        input_payload={"flow_name": name, **body.state},
        metadata={"db": db},
    )


@router.delete("/flows/{name}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_flow(request: Request, name: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.flow_registry import delete_dynamic_flow

    removed = delete_dynamic_flow(name, db=db)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Flow {name!r} not found or is a static flow (only dynamic flows can be deleted)")
    return None

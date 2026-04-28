from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.schemas import NodeRegistration
from AINDY.services.auth_service import get_current_user

router = APIRouter()


def _execute_nodes(request: Request, route_name: str, handler, *, db: Session | None = None, user_id: str, input_payload=None, success_status_code: int = 200):
    metadata = {"source": "platform.nodes"}
    if db is not None:
        metadata["db"] = db
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata=metadata,
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
        data.pop("execution_envelope", None)
    return data


@router.post("/nodes/register", status_code=201, response_model=None)
@limiter.limit("30/minute")
def register_node(request: Request, body: NodeRegistration, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from AINDY.platform_layer.node_registry import register_external_node

        try:
            return register_external_node(
                name=body.name,
                node_type=body.type,
                handler=body.handler,
                timeout_seconds=body.timeout_seconds,
                secret=body.secret,
                user_id=user_id,
                overwrite=body.overwrite,
                db=db,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc)})

    return _execute_nodes(request, "platform.nodes.register", handler, db=db, user_id=user_id, input_payload=body.model_dump(), success_status_code=201)


@router.get("/nodes", response_model=None)
@limiter.limit("60/minute")
def list_nodes(request: Request, current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.node_registry import list_dynamic_nodes

        return {"nodes": list_dynamic_nodes()}

    return _execute_nodes(request, "platform.nodes.list", handler, user_id=str(current_user["sub"]))


@router.get("/nodes/{name}", response_model=None)
@limiter.limit("60/minute")
def get_node(request: Request, name: str, current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.node_registry import get_dynamic_node

        meta = get_dynamic_node(name)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
        return meta

    return _execute_nodes(request, "platform.nodes.get", handler, user_id=str(current_user["sub"]), input_payload={"name": name})


@router.delete("/nodes/{name}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_node(request: Request, name: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.node_registry import delete_dynamic_node

        removed = delete_dynamic_node(name, db=db)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Node {name!r} not found or is a static node (only dynamic nodes can be deleted)")
        return None

    return _execute_nodes(request, "platform.nodes.delete", handler, db=db, user_id=str(current_user["sub"]), input_payload={"name": name}, success_status_code=204)

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.schemas import NodeRegistration
from AINDY.services.auth_service import get_current_user

router = APIRouter()


@router.post("/nodes/register", status_code=201, response_model=None)
@limiter.limit("30/minute")
def register_node(request: Request, body: NodeRegistration, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.node_registry import register_external_node

    user_id = str(current_user["sub"])
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


@router.get("/nodes", response_model=None)
@limiter.limit("60/minute")
def list_nodes(request: Request, current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.node_registry import list_dynamic_nodes

    return {"nodes": list_dynamic_nodes()}


@router.get("/nodes/{name}", response_model=None)
@limiter.limit("60/minute")
def get_node(request: Request, name: str, current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.node_registry import get_dynamic_node

    meta = get_dynamic_node(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    return meta


@router.delete("/nodes/{name}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_node(request: Request, name: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.node_registry import delete_dynamic_node

    removed = delete_dynamic_node(name, db=db)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found or is a static node (only dynamic nodes can be deleted)")
    return None

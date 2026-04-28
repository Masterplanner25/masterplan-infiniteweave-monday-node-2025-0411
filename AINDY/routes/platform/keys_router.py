from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.schemas import APIKeyCreate
from AINDY.services.auth_service import get_current_user

router = APIRouter()


def _execute_keys(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None, success_status_code: int = 200):
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata={"db": db, "source": "platform.keys"},
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


@router.post("/keys", status_code=201, response_model=None)
@limiter.limit("10/minute")
def create_key(request: Request, body: APIKeyCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.auth.api_key_auth import Scopes
        from AINDY.platform_layer.api_key_service import create_api_key

        invalid = [scope for scope in body.scopes if scope not in Scopes.ALL]
        if invalid:
            raise HTTPException(status_code=422, detail={"error": f"Unknown scopes: {invalid}. Valid: {Scopes.ALL}"})

        expires_at = None
        if body.expires_at:
            try:
                expires_at = datetime.fromisoformat(body.expires_at)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(status_code=422, detail={"error": "expires_at must be a valid ISO 8601 datetime string"})

        record, raw_key = create_api_key(
            user_id=str(current_user["sub"]),
            name=body.name,
            scopes=body.scopes,
            db=db,
            expires_at=expires_at,
        )
        return {
            "key": raw_key,
            "id": str(record.id),
            "name": record.name,
            "key_prefix": record.key_prefix,
            "scopes": list(record.scopes or []),
            "is_active": record.is_active,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    return _execute_keys(request, "platform.keys.create", handler, db=db, user_id=str(current_user["sub"]), input_payload=body.model_dump(), success_status_code=201)


@router.get("/keys", response_model=None)
@limiter.limit("60/minute")
def list_keys(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.api_key_service import list_api_keys

        return {"keys": list_api_keys(user_id=str(current_user["sub"]), db=db)}

    return _execute_keys(request, "platform.keys.list", handler, db=db, user_id=str(current_user["sub"]))


@router.get("/keys/{key_id}", response_model=None)
@limiter.limit("60/minute")
def get_key(request: Request, key_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.api_key_service import get_api_key

        meta = get_api_key(key_id=key_id, user_id=str(current_user["sub"]), db=db)
        if not meta:
            raise HTTPException(status_code=404, detail=f"API key {key_id!r} not found")
        return meta

    return _execute_keys(request, "platform.keys.get", handler, db=db, user_id=str(current_user["sub"]), input_payload={"key_id": key_id})


@router.delete("/keys/{key_id}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def revoke_key(request: Request, key_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.api_key_service import revoke_api_key

        revoked = revoke_api_key(key_id=key_id, user_id=str(current_user["sub"]), db=db)
        if not revoked:
            raise HTTPException(status_code=404, detail=f"API key {key_id!r} not found")
        return None

    return _execute_keys(request, "platform.keys.revoke", handler, db=db, user_id=str(current_user["sub"]), input_payload={"key_id": key_id}, success_status_code=204)

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.schemas import SyscallDispatchRequest
from AINDY.services.auth_service import get_current_user

router = APIRouter()


def _execute_platform_ops(request: Request, route_name: str, handler, *, db: Session | None = None, user_id: str, input_payload=None):
    metadata = {"source": "platform.ops"}
    if db is not None:
        metadata["db"] = db
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata=metadata,
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


class RotateSecretKeyRequest(BaseModel):
    new_key: str


@router.get("/nodus/trace/{trace_id}", response_model=None)
@limiter.limit("60/minute")
def get_nodus_trace(request: Request, trace_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user), limit: int = 500):
    def handler(ctx):
        from AINDY.runtime.nodus_trace_service import query_nodus_trace

        result = query_nodus_trace(db=db, trace_id=trace_id, user_id=str(current_user["sub"]), limit=limit)
        if result["count"] == 0:
            raise HTTPException(status_code=404, detail={"error": "trace_not_found", "message": f"No trace events found for trace_id {trace_id!r}. The execution may not have called any host functions, may belong to another user, or may not exist."})
        return result

    return _execute_platform_ops(request, "platform.nodus.trace.get", handler, db=db, user_id=str(current_user["sub"]), input_payload={"trace_id": trace_id, "limit": limit})


@router.get("/tenants/{tenant_id}/usage", response_model=None)
@limiter.limit("60/minute")
def get_tenant_usage(request: Request, tenant_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    def handler(ctx):
        caller_id = str(current_user["sub"])
        if caller_id != tenant_id:
            raise HTTPException(status_code=403, detail={"error": "TENANT_VIOLATION", "message": f"Caller {caller_id!r} is not authorised to view usage for tenant {tenant_id!r}"})

        from AINDY.kernel.resource_manager import get_resource_manager
        from AINDY.kernel.scheduler_engine import get_scheduler_engine

        summary = get_resource_manager().get_tenant_summary(tenant_id)
        summary["scheduler"] = get_scheduler_engine().stats()
        return summary

    return _execute_platform_ops(request, "platform.tenants.usage.get", handler, db=db, user_id=str(current_user["sub"]), input_payload={"tenant_id": tenant_id})


@router.get("/memory", response_model=None)
@limiter.limit("60/minute")
def list_memory_path(request: Request, path: str, limit: int = 50, query: Optional[str] = None, tags: Optional[str] = None, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    def handler(ctx):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.memory_address_space import normalize_path, validate_tenant_path

        user_id = str(current_user["sub"])
        try:
            norm = normalize_path(path)
            validate_tenant_path(norm, user_id)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})
        tag_list = [tag.strip() for tag in tags.split(",")] if tags else None
        nodes = MemoryNodeDAO(db).query_path(path_expr=norm, query=query, tags=tag_list, user_id=user_id, limit=limit)
        return {"nodes": nodes, "count": len(nodes), "path": norm}

    return _execute_platform_ops(request, "platform.memory.list", handler, db=db, user_id=str(current_user["sub"]), input_payload={"path": path, "limit": limit, "query": query, "tags": tags})


@router.get("/memory/tree", response_model=None)
@limiter.limit("60/minute")
def memory_tree(request: Request, path: str, limit: int = 200, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    def handler(ctx):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.memory_address_space import build_tree, is_exact, normalize_path, validate_tenant_path, wildcard_prefix

        user_id = str(current_user["sub"])
        try:
            norm = normalize_path(path)
            validate_tenant_path(norm, user_id)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})
        prefix = norm if is_exact(norm) else wildcard_prefix(norm)
        nodes = MemoryNodeDAO(db).walk_path(prefix, user_id=user_id, limit=limit)
        return {"tree": build_tree(nodes), "node_count": len(nodes), "path": norm}

    return _execute_platform_ops(request, "platform.memory.tree", handler, db=db, user_id=str(current_user["sub"]), input_payload={"path": path, "limit": limit})


@router.get("/memory/trace", response_model=None)
@limiter.limit("60/minute")
def memory_trace(request: Request, path: str, depth: int = 5, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    def handler(ctx):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.memory_address_space import normalize_path, validate_tenant_path

        user_id = str(current_user["sub"])
        try:
            norm = normalize_path(path)
            validate_tenant_path(norm, user_id)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})
        chain = MemoryNodeDAO(db).causal_trace(path=norm, depth=min(depth, 20), user_id=user_id)
        if not chain:
            raise HTTPException(status_code=404, detail={"error": "No node found at path"})
        return {"chain": chain, "depth": len(chain), "path": norm}

    return _execute_platform_ops(request, "platform.memory.trace", handler, db=db, user_id=str(current_user["sub"]), input_payload={"path": path, "depth": depth})


@router.get("/syscalls", response_model=None)
@limiter.limit("60/minute")
def list_syscalls(request: Request, version: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY
        from AINDY.kernel.syscall_versioning import SyscallSpec

        versioned = SYSCALL_REGISTRY.versioned
        available_versions = SYSCALL_REGISTRY.versions()
        if version:
            if version not in versioned:
                raise HTTPException(status_code=404, detail={"error": f"Unknown syscall version: {version!r}"})
            versioned = {version: versioned[version]}

        result: dict[str, dict] = {}
        total = 0
        for ver, actions in versioned.items():
            result[ver] = {}
            for action, entry in sorted(actions.items()):
                result[ver][action] = SyscallSpec(
                    name=action,
                    version=ver,
                    capability=entry.capability,
                    description=entry.description,
                    input_schema=entry.input_schema,
                    output_schema=entry.output_schema,
                    stable=entry.stable,
                    deprecated=entry.deprecated,
                    deprecated_since=entry.deprecated_since,
                    replacement=entry.replacement,
                ).to_dict()
                total += 1
        return {"versions": available_versions if not version else [version], "syscalls": result, "total_count": total}

    return _execute_platform_ops(request, "platform.syscalls.list", handler, user_id=str(current_user["sub"]), input_payload={"version": version})


@router.post("/syscall", response_model=None)
@limiter.limit("30/minute")
def dispatch_syscall(request: Request, body: SyscallDispatchRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    def handler(ctx):
        from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
        from AINDY.kernel.syscall_registry import DEFAULT_NODUS_CAPABILITIES

        user_id = str(current_user.get("user_id") or current_user.get("sub") or "")
        if current_user.get("auth_type") == "api_key":
            api_key_scopes = current_user.get("api_key_scopes") or []
            capabilities = [scope for scope in api_key_scopes if scope in DEFAULT_NODUS_CAPABILITIES]
        else:
            capabilities = list(DEFAULT_NODUS_CAPABILITIES)
        syscall_ctx = make_syscall_ctx_from_tool(user_id=user_id, capabilities=capabilities)
        result = get_dispatcher().dispatch(body.name, body.payload, syscall_ctx)
        if result["status"] == "error":
            msg = result.get("error", "syscall error")
            if "Permission denied" in msg or "capability" in msg:
                raise HTTPException(status_code=403, detail={"error": msg})
            if "Input validation failed" in msg:
                raise HTTPException(status_code=422, detail={"error": msg})
            if "quota" in msg.lower() or "QUOTA" in msg:
                raise HTTPException(status_code=429, detail={"error": msg})
            if "Unknown syscall" in msg:
                raise HTTPException(status_code=404, detail={"error": msg})
        return result

    return _execute_platform_ops(request, "platform.syscall.dispatch", handler, db=db, user_id=str(current_user.get("user_id") or current_user.get("sub") or ""), input_payload=body.model_dump())


@router.post("/ops/rotate-secret-key", response_model=None)
@limiter.limit("10/minute")
def rotate_secret_key(
    request: Request,
    body: RotateSecretKeyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    def handler(ctx):
        if len(body.new_key or "") < 32:
            raise HTTPException(status_code=400, detail="new_key must be at least 32 characters")

        from AINDY.core.system_event_service import emit_system_event
        from AINDY.services import auth_service

        if body.new_key == auth_service._key_ring.active_key:
            raise HTTPException(status_code=400, detail="new_key is the same as the current active key")

        auth_service.rotate_signing_key(body.new_key)
        emit_system_event(
            db=db,
            event_type="platform.secret_key.rotated",
            user_id=str(current_user.get("sub") or current_user.get("user_id") or ""),
            payload={"message": "rotation completed"},
            required=False,
        )
        return {
            "rotated": True,
            "grace_hours": auth_service._key_ring._grace_hours,
            "message": (
                f"New key active. Previous key valid for {auth_service._key_ring._grace_hours} hours."
            ),
        }

    return _execute_platform_ops(request, "platform.secret_key.rotate", handler, db=db, user_id=str(current_user.get("sub") or current_user.get("user_id") or ""), input_payload=body.model_dump())

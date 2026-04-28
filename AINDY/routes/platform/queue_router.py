from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from AINDY.core.distributed_queue import QueueJobPayload, get_queue, get_queue_health_snapshot
from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

router = APIRouter()


def _list_dead_letters(limit: int | None = None) -> tuple[str, list[dict]]:
    backend = get_queue()
    if hasattr(backend, "peek_dead_letters") and backend.backend_name == "redis":
        size = backend.get_dlq_depth() if limit is None else limit
        items = backend.peek_dead_letters(size)  # type: ignore[attr-defined]
    else:
        items = backend.get_dead_letters()  # type: ignore[attr-defined]
        if limit is not None:
            items = items[:limit]
    return backend.backend_name, list(items)


@router.get("/queue/health", response_model=None)
@limiter.limit("60/minute")
async def get_queue_health(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return get_queue_health_snapshot()

    return await execute_with_pipeline(
        request=request,
        route_name="platform.queue.health",
        handler=handler,
        user_id=str(current_user["sub"]),
        input_payload={},
        metadata={"source": "platform.queue"},
    )


@router.get("/queue/dead-letters", response_model=None)
@limiter.limit("60/minute")
async def list_dead_letters(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        backend_name, items = _list_dead_letters(limit)
        return {"count": len(items), "items": items, "backend": backend_name}

    return await execute_with_pipeline(
        request=request,
        route_name="platform.queue.dead_letters.list",
        handler=handler,
        user_id=str(current_user["sub"]),
        input_payload={"limit": limit},
        metadata={"source": "platform.queue"},
    )


@router.post("/queue/dead-letters/drain", response_model=None)
@limiter.limit("30/minute")
async def drain_dead_letters(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        drained = get_queue().drain_dead_letters()
        return {"drained": drained}

    return await execute_with_pipeline(
        request=request,
        route_name="platform.queue.dead_letters.drain",
        handler=handler,
        user_id=str(current_user["sub"]),
        input_payload={},
        metadata={"source": "platform.queue"},
    )


@router.post("/queue/dead-letters/{job_id}/replay", response_model=None)
@limiter.limit("30/minute")
async def replay_dead_letter(
    request: Request,
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        _, items = _list_dead_letters()
        match = next((entry for entry in items if entry.get("job_id") == job_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="Dead-lettered job not found")
        payload_raw = match.get("payload_raw")
        if not isinstance(payload_raw, str) or not payload_raw:
            raise HTTPException(status_code=400, detail="Dead-lettered job payload is unavailable")
        payload = QueueJobPayload.from_json(payload_raw)
        get_queue().enqueue(payload)
        return {"replayed": True, "job_id": job_id}

    return await execute_with_pipeline(
        request=request,
        route_name="platform.queue.dead_letters.replay",
        handler=handler,
        user_id=str(current_user["sub"]),
        input_payload={"job_id": job_id},
        metadata={"source": "platform.queue"},
    )


@router.delete("/queue/dead-letters/{job_id}", response_model=None)
@limiter.limit("30/minute")
async def delete_dead_letter(
    request: Request,
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        removed = get_queue().remove_dead_letter(job_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Dead-lettered job not found")
        return {"removed": True, "job_id": job_id}

    return await execute_with_pipeline(
        request=request,
        route_name="platform.queue.dead_letters.delete",
        handler=handler,
        user_id=str(current_user["sub"]),
        input_payload={"job_id": job_id},
        metadata={"source": "platform.queue"},
    )

from __future__ import annotations

import uuid

from fastapi import HTTPException


def get_task_graph_context_via_syscall(user_id, db) -> dict:
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=["task.read"],
        trace_id="",
        metadata={"_db": db},
    )
    try:
        result = get_dispatcher().dispatch(
            "sys.v1.tasks.get_graph_context",
            {"user_id": str(user_id)},
            ctx,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "syscall_unavailable", "message": str(exc)},
        ) from exc
    if result["status"] != "success":
        raise HTTPException(
            status_code=503,
            detail={"error": "syscall_unavailable", "message": result.get("error", "")},
        )
    return dict(result.get("data") or {})

from __future__ import annotations

import uuid

from fastapi import HTTPException


def _dispatch(name: str, payload: dict, *, user_id: str, db, capabilities: list[str]) -> dict:
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=capabilities,
        trace_id="",
        metadata={"_db": db},
    )
    try:
        result = get_dispatcher().dispatch(name, payload, ctx)
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
    return result["data"]


def get_kpi_snapshot_via_syscall(user_id, db) -> dict:
    return dict(
        _dispatch(
            "sys.v1.analytics.get_kpi_snapshot",
            {"user_id": str(user_id)},
            user_id=str(user_id),
            db=db,
            capabilities=["analytics.read"],
        )
        or {}
    )


def save_calculation_via_syscall(db, metric_name: str, value: float, *, user_id: str | None = None) -> dict:
    return dict(
        _dispatch(
            "sys.v1.analytics.save_calculation",
            {"metric_name": metric_name, "value": value, "user_id": user_id},
            user_id=str(user_id or ""),
            db=db,
            capabilities=["analytics.write"],
        )
        or {}
    )

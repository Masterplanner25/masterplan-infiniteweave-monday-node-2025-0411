from __future__ import annotations

import uuid

from fastapi import HTTPException


def get_eta_via_syscall(masterplan_id, user_id: str, db):
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=["masterplan.read"],
        trace_id="",
        metadata={"_db": db},
    )
    try:
        result = get_dispatcher().dispatch(
            "sys.v1.masterplan.get_eta",
            {"masterplan_id": str(masterplan_id), "user_id": str(user_id)},
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
    return (result.get("data") or {}).get("eta")

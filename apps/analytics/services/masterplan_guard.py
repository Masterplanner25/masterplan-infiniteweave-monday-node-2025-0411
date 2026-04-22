"""
Cross-domain guard helper: analytics → masterplan ownership check via syscall.

Analytics routes must not depend directly on masterplan service modules.
This module provides assert_masterplan_owned_via_syscall() as the
compliant alternative, routing through the syscall dispatcher.
"""
from __future__ import annotations


def assert_masterplan_owned_via_syscall(
    masterplan_id,
    user_id: str,
    db,
) -> None:
    """Assert that user_id owns masterplan_id via the syscall layer.

    Raises HTTPException(404) if not found or not owned — matching the
    behaviour of the underlying assert_masterplan_owned() service function.

    Args:
        masterplan_id: MasterPlan primary key (int or str).
        user_id:       Authenticated user ID string.
        db:            Active SQLAlchemy Session (shared with the caller).
    """
    import uuid

    from fastapi import HTTPException

    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=["masterplan.read"],
        trace_id="",
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.masterplan.assert_owned",
        {"masterplan_id": str(masterplan_id), "user_id": str(user_id)},
        ctx,
    )
    if result["status"] != "success":
        error_msg = result.get("error", "")
        if error_msg.startswith("NOT_FOUND:"):
            detail_msg = error_msg[len("NOT_FOUND:"):]
            raise HTTPException(
                status_code=404,
                detail={"error": "masterplan_not_found", "message": detail_msg},
            )
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": error_msg},
        )

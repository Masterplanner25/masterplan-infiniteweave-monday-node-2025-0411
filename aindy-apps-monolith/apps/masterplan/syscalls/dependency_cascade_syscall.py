from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _handle_masterplan_cascade_activate(
    payload: dict, context: SyscallContext
) -> dict:
    """
    sys.v1.masterplan.cascade_activate
    Evaluate dependency graph and activate all ready tasks.
    """
    from AINDY.db.database import SessionLocal
    from apps.masterplan.services.dependency_cascade import activate_ready_tasks

    masterplan_id = payload.get("masterplan_id")
    user_id = payload.get("user_id") or (context.user_id and str(context.user_id))
    if not masterplan_id:
        raise ValueError("sys.v1.masterplan.cascade_activate requires 'masterplan_id'")
    if not user_id:
        raise ValueError("sys.v1.masterplan.cascade_activate requires 'user_id'")

    external_db = context.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        activated = activate_ready_tasks(db, masterplan_id, user_id)
        return {"activated_task_ids": activated, "count": len(activated)}
    finally:
        if owns_session:
            db.close()


def register_dependency_cascade_syscalls() -> None:
    register_syscall(
        "sys.v1.masterplan.cascade_activate",
        _handle_masterplan_cascade_activate,
        "masterplan.cascade_activate",
        "Evaluate dependency graph and activate all ready tasks in a masterplan",
        input_schema={
            "required": ["masterplan_id"],
            "properties": {
                "masterplan_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
        },
        stable=False,
    )

"""
Masterplan domain syscall handlers.

Registers sys.v1.masterplan.* syscalls. Called once at startup via
register_masterplan_syscall_handlers() which is invoked from apps/bootstrap.py.
"""
from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _handle_assert_masterplan_owned(payload: dict, ctx: SyscallContext) -> dict:
    """sys.v1.masterplan.assert_owned — verify user owns the given MasterPlan.

    Payload keys:
        masterplan_id  (str | int) — required
        user_id        (str)       — required

    Context metadata keys (optional):
        _db — caller-provided SQLAlchemy Session (transaction preserved).

    Returns:
        {"owned": True, "masterplan_id": str} on success.

    Raises:
        ValueError with prefix "NOT_FOUND:" when plan is missing or not owned.
    """
    from fastapi import HTTPException

    from AINDY.db.database import SessionLocal
    from apps.masterplan.services.masterplan_service import assert_masterplan_owned

    masterplan_id = payload["masterplan_id"]
    user_id = payload["user_id"]

    external_db = ctx.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        assert_masterplan_owned(db, masterplan_id, user_id)
        return {"owned": True, "masterplan_id": str(masterplan_id)}
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            message = detail.get("message", str(detail))
        else:
            message = str(detail)
        if exc.status_code == 404:
            raise ValueError(f"NOT_FOUND:{message}") from exc
        raise ValueError(f"FORBIDDEN:{message}") from exc
    finally:
        if owns_session:
            db.close()


def register_masterplan_syscall_handlers() -> None:
    """Register all masterplan domain syscall handlers.

    Called once at application startup from apps/bootstrap.py.
    Safe to call multiple times — idempotent.
    """
    register_syscall(
        name="sys.v1.masterplan.assert_owned",
        handler=_handle_assert_masterplan_owned,
        capability="masterplan.read",
        description="Assert that the given user owns the given MasterPlan.",
        input_schema={
            "required": ["masterplan_id", "user_id"],
            "properties": {
                "masterplan_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["owned"],
            "properties": {
                "owned": {"type": "bool"},
                "masterplan_id": {"type": "string"},
            },
        },
        stable=False,
    )
    logger.info("[masterplan_syscalls] registered sys.v1.masterplan.assert_owned")

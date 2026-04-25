"""Rippletrace domain syscall handlers."""
from __future__ import annotations

import uuid

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall


def _session_from_context(ctx: SyscallContext):
    from AINDY.db.database import SessionLocal

    external_db = ctx.metadata.get("_db") or ctx.metadata.get("db")
    if external_db is not None:
        return external_db, False
    return SessionLocal(), True


def _handle_rippletrace_list_pings(payload: dict, ctx: SyscallContext) -> dict:
    from apps.rippletrace.models import PingDB

    user_id = payload.get("user_id") or ctx.user_id
    limit = int(payload.get("limit") or 10)

    db, owns_session = _session_from_context(ctx)
    try:
        pings = (
            db.query(PingDB)
            .filter(PingDB.user_id == uuid.UUID(str(user_id)))
            .order_by(PingDB.date_detected.desc())
            .limit(limit)
            .all()
        )
        return {
            "pings": [
                {
                    "ping_type": ping.ping_type,
                    "source_platform": ping.source_platform,
                    "summary": ping.connection_summary,
                    "date_detected": ping.date_detected.isoformat() if ping.date_detected else None,
                }
                for ping in pings
            ]
        }
    finally:
        if owns_session:
            db.close()


def register_rippletrace_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.rippletrace.list_recent_pings",
        handler=_handle_rippletrace_list_pings,
        capability="rippletrace.read",
        description="List recent pings for a user.",
        stable=False,
    )

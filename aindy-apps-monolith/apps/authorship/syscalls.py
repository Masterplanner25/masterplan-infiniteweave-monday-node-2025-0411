"""Authorship domain syscall handlers."""
from __future__ import annotations

import uuid

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall


def _session_from_context(ctx: SyscallContext):
    from AINDY.db.database import SessionLocal

    external_db = ctx.metadata.get("_db") or ctx.metadata.get("db")
    if external_db is not None:
        return external_db, False
    return SessionLocal(), True


def _handle_authorship_list(payload: dict, ctx: SyscallContext) -> dict:
    from apps.authorship.models import AuthorDB

    user_id = payload.get("user_id") or ctx.user_id
    limit = int(payload.get("limit") or 10)

    db, owns_session = _session_from_context(ctx)
    try:
        authors = (
            db.query(AuthorDB)
            .filter(AuthorDB.user_id == uuid.UUID(str(user_id)))
            .order_by(AuthorDB.joined_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "authors": [
                {
                    "id": author.id,
                    "name": author.name,
                    "platform": author.platform,
                    "last_seen": author.last_seen.isoformat() if author.last_seen else None,
                    "notes": author.notes,
                }
                for author in authors
            ]
        }
    finally:
        if owns_session:
            db.close()


def register_authorship_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.authorship.list_authors",
        handler=_handle_authorship_list,
        capability="authorship.read",
        description="List recent authors for a user.",
        stable=False,
    )

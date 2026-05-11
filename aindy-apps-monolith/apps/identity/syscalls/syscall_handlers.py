"""Identity domain syscall handlers."""
from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _handle_get_identity_context(payload: dict, ctx: SyscallContext) -> dict:
    """Return identity context for prompt injection."""
    from AINDY.db.database import SessionLocal
    from apps.identity.services.identity_service import IdentityService

    user_id = payload.get("user_id") or ctx.user_id
    if not user_id:
        return {"context": ""}

    db = SessionLocal()
    try:
        service = IdentityService(db=db, user_id=str(user_id))
        context_str = service.get_context_for_prompt()
        return {"context": context_str or ""}
    except Exception as exc:
        logger.warning(
            "[identity_syscall] get_context failed for user=%s: %s",
            user_id,
            exc,
        )
        return {"context": ""}
    finally:
        db.close()


def _handle_observe_identity(payload: dict, ctx: SyscallContext) -> dict:
    """Record an identity observation event."""
    from AINDY.db.database import SessionLocal
    from apps.identity.services.identity_service import IdentityService

    user_id = payload.get("user_id") or ctx.user_id
    event_type = payload.get("event_type")
    context = payload.get("context") or {}

    if not user_id or not event_type:
        return {"observed": False}

    db = SessionLocal()
    try:
        service = IdentityService(db=db, user_id=str(user_id))
        service.observe(event_type=event_type, context=context)
        return {"observed": True}
    except Exception as exc:
        logger.warning(
            "[identity_syscall] observe failed for user=%s event=%s: %s",
            user_id,
            event_type,
            exc,
        )
        return {"observed": False}
    finally:
        db.close()


def register_identity_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.identity.get_context",
        handler=_handle_get_identity_context,
        capability="identity.read",
        description="Return identity context string for prompt injection.",
        input_schema={
            "properties": {"user_id": {"type": "string"}},
        },
        output_schema={
            "required": ["context"],
            "properties": {"context": {"type": "string"}},
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.identity.observe",
        handler=_handle_observe_identity,
        capability="identity.write",
        description="Record an identity observation event.",
        input_schema={
            "required": ["event_type"],
            "properties": {
                "user_id": {"type": "string"},
                "event_type": {"type": "string"},
                "context": {"type": "dict"},
            },
        },
        output_schema={
            "required": ["observed"],
            "properties": {"observed": {"type": "bool"}},
        },
        stable=False,
    )
    logger.info(
        "[identity_syscalls] registered sys.v1.identity.get_context and observe"
    )

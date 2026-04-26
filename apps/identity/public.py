"""
Public surface for the identity domain.
All cross-domain callers must use these functions - never import
from identity.services.* directly.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

PUBLIC_API_VERSION = "1.0"

__all__ = [
    "get_context_for_prompt",
    "get_recent_memory",
    "get_user_metrics",
    "observe_identity_event",
]


def get_context_for_prompt(user_id: str, db: Session) -> str:
    """
    Return an LLM-injectable context string for this user's identity profile.
    Returns empty string if identity data is unavailable.
    """
    try:
        from apps.identity.services.identity_service import IdentityService

        service = IdentityService(db=db, user_id=user_id)
        return service.get_context_for_prompt()
    except Exception:
        return ""


def get_recent_memory(
    user_id: str,
    db: Session,
    *,
    context: str = "infinity_loop",
) -> list[dict[str, Any]]:
    """
    Return recent memory items for a user in the given context.
    Returns empty list if unavailable.
    """
    try:
        from apps.identity.services.identity_boot_service import get_recent_memory as _fn

        return list(_fn(user_id, db, context=context) or [])
    except Exception:
        return []


def get_user_metrics(user_id: str, db: Session) -> dict[str, Any]:
    """
    Return user-level metrics dict for the given user_id.
    Returns empty dict if unavailable.
    """
    try:
        from apps.identity.services.identity_boot_service import get_user_metrics as _fn

        return dict(_fn(user_id, db) or {})
    except Exception:
        return {}


def observe_identity_event(
    user_id: str,
    db: Session,
    *,
    event_type: str,
    context: dict[str, Any],
) -> bool:
    """
    Record an identity inference event for this user.
    Returns false if the identity layer is unavailable.
    """
    try:
        from apps.identity.services.identity_service import IdentityService

        service = IdentityService(db=db, user_id=user_id)
        service.observe(event_type=event_type, context=context)
        return True
    except Exception:
        return False

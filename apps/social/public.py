"""
Public surface for the social domain.
Consumers: analytics
"""

from __future__ import annotations

from typing import Any

PUBLIC_API_VERSION = "1.0"


def adapt_linkedin_metrics(raw: Any) -> dict[str, Any]:
    from apps.social.services.linkedin_adapter import linkedin_adapter

    return dict(linkedin_adapter(raw) or {})


def get_social_performance_signals(
    *,
    user_id: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    from apps.social.services.social_performance_service import (
        get_social_performance_signals as _get_social_performance_signals,
    )

    return list(_get_social_performance_signals(user_id=user_id, limit=limit) or [])


__all__ = [
    "adapt_linkedin_metrics",
    "get_social_performance_signals",
]

"""
Public surface for the authorship domain.
Consumers: network_bridge, automation
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

PUBLIC_API_VERSION = "1.0"


def _serialize_scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _author_to_dict(row) -> dict[str, Any]:
    return {
        key: _serialize_scalar(value)
        for key, value in row.__dict__.items()
        if not key.startswith("_")
    }


def register_author(
    db: Session,
    *,
    name: str,
    platform: str,
    notes: str | None = None,
    user_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    from apps.authorship.services.author_directory_service import upsert_author

    return _author_to_dict(
        upsert_author(
            db,
            name=name,
            platform=platform,
            notes=notes,
            user_id=user_id,
        )
    )


def list_authors(
    db: Session,
    *,
    platform: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    from apps.authorship.services.author_directory_service import (
        list_authors as _list_authors,
    )

    return [_author_to_dict(row) for row in _list_authors(db, platform=platform, limit=limit)]


__all__ = [
    "register_author",
    "list_authors",
]

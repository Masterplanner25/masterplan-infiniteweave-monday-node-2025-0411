from __future__ import annotations

import uuid
from typing import Iterable


def parse_user_id(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def require_user_id(value: str | uuid.UUID | None) -> uuid.UUID:
    parsed = parse_user_id(value)
    if parsed is None:
        raise ValueError("user_id is required")
    return parsed


def parse_user_ids(values: Iterable[str | uuid.UUID | None]) -> list[uuid.UUID]:
    parsed: list[uuid.UUID] = []
    for value in values:
        user_id = parse_user_id(value)
        if user_id is not None:
            parsed.append(user_id)
    return parsed

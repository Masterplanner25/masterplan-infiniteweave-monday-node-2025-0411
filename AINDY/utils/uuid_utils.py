from __future__ import annotations

from uuid import UUID


def normalize_uuid(value):
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))

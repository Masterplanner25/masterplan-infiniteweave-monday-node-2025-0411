from __future__ import annotations

from typing import Optional, Tuple


class NoOpCacheBackend:
    """Cache backend that always misses and never persists values.

    Used for production-safe cache disablement when shared cache semantics are
    not available and instance-local caching would be misleading across nodes.
    """

    async def get_with_ttl(self, key: str) -> Tuple[int, Optional[bytes]]:
        return 0, None

    async def get(self, key: str) -> Optional[bytes]:
        return None

    async def set(self, key: str, value: bytes, expire: Optional[int] = None) -> None:
        return None

    async def clear(self, namespace: Optional[str] = None, key: Optional[str] = None) -> int:
        return 0

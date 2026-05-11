from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from AINDY.kernel.resume_spec import ResumeSpec

log = logging.getLogger(__name__)

_KEY_PREFIX = "aindy:wait:"
_DEFAULT_TTL = 86400


def _key(run_id: str) -> str:
    return f"{_KEY_PREFIX}{run_id}"


class RedisWaitRegistry:
    def __init__(self, redis_client=None):
        self._redis = redis_client

    def register(self, run_id: str, spec: "ResumeSpec") -> bool:
        """Write spec to Redis. Returns True on success, False if Redis unavailable."""
        if self._redis is None:
            return False
        try:
            from AINDY.kernel.resume_spec import spec_to_json

            self._redis.setex(_key(run_id), _DEFAULT_TTL, spec_to_json(spec))
            return True
        except Exception:
            log.warning(
                "RedisWaitRegistry.register failed for run_id=%s",
                run_id,
                exc_info=True,
            )
            return False

    def get_spec(self, run_id: str) -> "ResumeSpec | None":
        if self._redis is None:
            return None
        try:
            from AINDY.kernel.resume_spec import spec_from_json

            raw = self._redis.get(_key(run_id))
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return spec_from_json(raw) if raw else None
        except Exception:
            log.warning(
                "RedisWaitRegistry.get_spec failed for run_id=%s",
                run_id,
                exc_info=True,
            )
            return None

    def get_all_specs(self) -> dict[str, "ResumeSpec"]:
        """Return all waiting specs from Redis. Used for cross-instance recovery."""
        if self._redis is None:
            return {}
        try:
            from AINDY.kernel.resume_spec import spec_from_json

            results: dict[str, ResumeSpec] = {}
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(
                    cursor=cursor,
                    match=f"{_KEY_PREFIX}*",
                    count=100,
                )
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                    raw = self._redis.get(key)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    if raw:
                        run_id = key_str.removeprefix(_KEY_PREFIX)
                        try:
                            results[run_id] = spec_from_json(raw)
                        except Exception:
                            pass
                if cursor == 0 or cursor == "0":
                    break
            return results
        except Exception:
            log.warning("RedisWaitRegistry.get_all_specs failed", exc_info=True)
            return {}

    def unregister(self, run_id: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(_key(run_id))
        except Exception:
            log.warning(
                "RedisWaitRegistry.unregister failed for run_id=%s",
                run_id,
                exc_info=True,
            )

    def unregister_if_exists(self, run_id: str) -> bool:
        """Delete key and return True if it existed (claim succeeded)."""
        if self._redis is None:
            return False
        try:
            return bool(self._redis.delete(_key(run_id)))
        except Exception:
            log.warning(
                "RedisWaitRegistry.unregister_if_exists failed for run_id=%s",
                run_id,
                exc_info=True,
            )
            return False

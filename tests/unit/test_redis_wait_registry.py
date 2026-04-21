from __future__ import annotations

from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
from AINDY.kernel.resume_spec import RESUME_HANDLER_EU, ResumeSpec, spec_from_json


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str):
        self._values[key] = value
        self._ttls[key] = ttl
        return True

    def get(self, key: str):
        return self._values.get(key)

    def delete(self, key: str):
        self._values.pop(key, None)
        self._ttls.pop(key, None)
        return 1

    def scan(self, cursor=0, match=None, count=100):
        keys = sorted(self._values.keys())
        if match is not None:
            prefix = str(match).removesuffix("*")
            keys = [key for key in keys if key.startswith(prefix)]
        return 0, keys


def _spec(run_id: str) -> ResumeSpec:
    return ResumeSpec(
        handler=RESUME_HANDLER_EU,
        eu_id=f"eu-{run_id}",
        tenant_id=f"tenant-{run_id}",
        run_id=run_id,
        eu_type="flow",
    )


def test_register_stores_json_in_redis():
    redis = _FakeRedis()
    registry = RedisWaitRegistry(redis)

    ok = registry.register("run-1", _spec("run-1"))

    assert ok is True
    stored = redis.get("aindy:wait:run-1")
    assert stored is not None
    assert spec_from_json(stored) == _spec("run-1")


def test_get_spec_returns_none_when_missing():
    registry = RedisWaitRegistry(_FakeRedis())

    assert registry.get_spec("nonexistent") is None


def test_get_spec_returns_none_when_redis_unavailable():
    registry = RedisWaitRegistry(None)

    assert registry.get_spec("run-1") is None


def test_register_returns_false_when_redis_unavailable():
    registry = RedisWaitRegistry(None)

    assert registry.register("run-1", _spec("run-1")) is False


def test_unregister_removes_key():
    redis = _FakeRedis()
    registry = RedisWaitRegistry(redis)
    registry.register("run-1", _spec("run-1"))

    registry.unregister("run-1")

    assert redis.get("aindy:wait:run-1") is None


def test_get_all_specs_returns_all_registered():
    redis = _FakeRedis()
    registry = RedisWaitRegistry(redis)
    expected = {run_id: _spec(run_id) for run_id in ("run-1", "run-2", "run-3")}
    for run_id, spec in expected.items():
        registry.register(run_id, spec)

    results = registry.get_all_specs()

    assert results == expected


def test_redis_error_does_not_raise():
    class _BrokenRedis:
        def get(self, _key: str):
            raise RuntimeError("redis down")

    registry = RedisWaitRegistry(_BrokenRedis())

    assert registry.get_spec("run-1") is None

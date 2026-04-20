from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from AINDY.kernel.resource_manager import RedisResourceBackend, ResourceManager


class _Pipeline:
    def __init__(self, client) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple]] = []

    def incr(self, key: str):
        self._ops.append(("incr", (key,)))
        return self

    def expire(self, key: str, ttl: int):
        self._ops.append(("expire", (key, ttl)))
        return self

    def execute(self):
        for name, args in self._ops:
            getattr(self._client, name)(*args)
        return [None] * len(self._ops)


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, int] = {}
        self._ttls: dict[str, int] = {}

    def ping(self):
        return True

    def get(self, key: str):
        value = self._values.get(key)
        if value is None:
            return None
        return str(value)

    def incr(self, key: str):
        value = self._values.get(key, 0) + 1
        self._values[key] = value
        return value

    def decr(self, key: str):
        value = self._values.get(key, 0) - 1
        self._values[key] = value
        return value

    def expire(self, key: str, ttl: int):
        self._ttls[key] = ttl
        return True

    def pipeline(self):
        return _Pipeline(self)


def _build_fake_redis():
    try:
        import fakeredis

        return fakeredis.FakeRedis(decode_responses=True)
    except Exception:
        return _FakeRedis()


class TestResourceManagerRedisMode:
    def test_can_execute_enforces_quota_via_redis(self, monkeypatch):
        fake = _build_fake_redis()
        rm = ResourceManager()
        monkeypatch.setattr(rm, "_get_redis", lambda: fake)
        monkeypatch.setattr(rm, "MAX_CONCURRENT_PER_TENANT", 5)

        for i in range(5):
            rm.mark_started("tenant-1", f"eu-{i}")

        ok, reason = rm.can_execute("tenant-1", "eu-new")

        assert ok is False
        assert reason is not None
        assert "limit" in reason

    def test_can_execute_falls_back_to_local_when_redis_none(self, monkeypatch):
        rm = ResourceManager()
        monkeypatch.setattr(rm, "_get_redis", lambda: None)

        ok, reason = rm.can_execute("tenant-x", "eu-y")

        assert ok is True
        assert reason is None

    def test_mark_completed_uses_redis_counter(self, monkeypatch):
        fake = _build_fake_redis()
        rm = ResourceManager()
        monkeypatch.setattr(rm, "_get_redis", lambda: fake)

        rm.mark_started("tenant-a", "eu-1")
        rm.mark_completed("tenant-a", "eu-1")

        assert int(fake.get("aindy:rm:tenant:tenant-a:active") or 0) == 0

    def test_is_redis_mode_reflects_cached_client(self, monkeypatch):
        rm = ResourceManager()
        monkeypatch.setattr(rm, "_get_redis", lambda: object())
        assert rm.is_redis_mode() is True

        monkeypatch.setattr(rm, "_get_redis", lambda: None)
        assert rm.is_redis_mode() is False


def test_redis_failure_falls_through_to_local(monkeypatch):
    class _BrokenRedis:
        def get(self, _key):
            raise RuntimeError("redis down")

    rm = ResourceManager()
    monkeypatch.setattr(rm, "_get_redis", lambda: _BrokenRedis())
    rm._active_counts["tenant-a"] = 1

    assert rm.get_tenant_active("tenant-a") == 1


def test_eu_keys_expired():
    backend = MagicMock()
    backend.delete_eu.return_value = None

    with patch("AINDY.kernel.resource_manager._get_backend", return_value=backend):
        rm = ResourceManager()
        rm.mark_completed("tenant-a", "eu-1")

    backend.delete_eu.assert_called_once_with("eu-1")


def test_reset_clears_only_aindy_rm_keys():
    client = MagicMock()
    client.register_script.return_value = MagicMock(return_value=0)
    client.scan.side_effect = [
        ("1", ["aindy:rm:tenant:t1:active"]),
        ("0", ["aindy:rm:eu:eu-1:cpu_ms", "aindy:rm:eu:eu-1:syscalls"]),
    ]

    with patch("redis.from_url", return_value=client):
        backend = RedisResourceBackend("redis://example")

    backend.reset_all()

    assert client.scan.call_args_list == [
        call(cursor=0, match="aindy:rm:*", count=100),
        call(cursor="1", match="aindy:rm:*", count=100),
    ]
    assert client.flushdb.called is False

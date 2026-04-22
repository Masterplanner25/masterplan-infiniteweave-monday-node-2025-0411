from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend


def _reset_cache():
    FastAPICache.reset()


def test_dev_without_redis_uses_memory_cache(monkeypatch):
    from AINDY import main

    _reset_cache()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(main.settings, "ENV", "development")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "redis")
    monkeypatch.setattr(main.settings, "REDIS_URL", None)

    mode = main._initialize_cache_backend()

    assert mode == "memory"
    assert isinstance(FastAPICache.get_backend(), InMemoryBackend)


def test_production_memory_backend_disables_cache(monkeypatch):
    from AINDY import main
    from AINDY.platform_layer.cache_backend import NoOpCacheBackend

    _reset_cache()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "memory")

    mode = main._initialize_cache_backend()

    assert mode == "disabled"
    assert isinstance(FastAPICache.get_backend(), NoOpCacheBackend)


def test_production_redis_backend_without_redis_url_disables_cache(monkeypatch):
    from AINDY import main
    from AINDY.platform_layer.cache_backend import NoOpCacheBackend

    _reset_cache()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "redis")
    monkeypatch.setattr(main.settings, "REDIS_URL", None)

    mode = main._initialize_cache_backend()

    assert mode == "disabled"
    assert isinstance(FastAPICache.get_backend(), NoOpCacheBackend)


def test_cache_backend_failure_does_not_crash_production_runtime(monkeypatch):
    from AINDY import main
    from AINDY.platform_layer.cache_backend import NoOpCacheBackend

    _reset_cache()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "redis")
    monkeypatch.setattr(main.settings, "REDIS_URL", "redis://example")

    fake_redis_asyncio = SimpleNamespace(
        from_url=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("redis init failed"))
    )
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=fake_redis_asyncio))
    monkeypatch.setitem(sys.modules, "fastapi_cache.backends.redis", SimpleNamespace(RedisBackend=lambda redis: redis))

    mode = main._initialize_cache_backend()

    assert mode == "disabled"
    assert isinstance(FastAPICache.get_backend(), NoOpCacheBackend)

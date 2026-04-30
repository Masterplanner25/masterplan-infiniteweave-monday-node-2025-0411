from __future__ import annotations

import importlib
from unittest.mock import patch



def _counter_value(counter) -> float:
    return counter._value.get()


def _gauge_value(gauge) -> float:
    return gauge._value.get()


def test_drop_redis_client_updates_fallback_metrics():
    from AINDY.kernel.resource_manager import ResourceManager
    from AINDY.platform_layer.metrics import quota_redis_fallback_total, quota_redis_mode

    rm = ResourceManager()
    start_value = _counter_value(quota_redis_fallback_total)

    rm._drop_redis_client("redis lost: %s", RuntimeError("down"))

    assert _gauge_value(quota_redis_mode) == 0
    assert _counter_value(quota_redis_fallback_total) == start_value + 1


def test_get_redis_success_sets_mode_gauge(monkeypatch):
    import AINDY.kernel.resource_manager as resource_manager_module
    from AINDY.kernel.resource_manager import ResourceManager
    from AINDY.platform_layer.metrics import quota_redis_mode

    class _Client:
        def ping(self):
            return True

    class _RedisLib:
        @staticmethod
        def from_url(*args, **kwargs):
            return _Client()

    rm = ResourceManager()
    rm._redis_last_check = 0.0
    monkeypatch.setattr(resource_manager_module.settings, "REDIS_URL", "redis://example")

    with patch.dict("sys.modules", {"redis": _RedisLib}):
        client = rm._get_redis()

    assert client is not None
    assert _gauge_value(quota_redis_mode) == 1


def test_check_quota_backend_status_degraded_in_distributed_mode():
    health_router = importlib.import_module("AINDY.routes.health_router")

    class _RM:
        def is_redis_mode(self) -> bool:
            return False

    with patch.object(health_router.settings, "EXECUTION_MODE", "distributed"), patch(
        "AINDY.kernel.resource_manager.get_resource_manager",
        return_value=_RM(),
    ):
        status = health_router._check_quota_backend_status()

    assert status["status"] == "degraded"
    assert status["quota_mode"] == "in_memory"


def test_check_quota_backend_status_ok_in_thread_mode_without_redis():
    health_router = importlib.import_module("AINDY.routes.health_router")

    class _RM:
        def is_redis_mode(self) -> bool:
            return False

    with patch.object(health_router.settings, "EXECUTION_MODE", "thread"), patch(
        "AINDY.kernel.resource_manager.get_resource_manager",
        return_value=_RM(),
    ):
        status = health_router._check_quota_backend_status()

    assert status["status"] == "ok"
    assert status["quota_mode"] == "in_memory"

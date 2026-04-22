from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


class _StopStartup(Exception):
    pass


def _patch_minimal_lifespan(monkeypatch, main):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("AINDY_ENFORCE_SCHEMA", "false")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "SECRET_KEY", "deployment-contract-test-secret-key-32chars")
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "memory")
    monkeypatch.setattr(main.FastAPICache, "init", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "ensure_mongo_ready", lambda **kwargs: None)
    monkeypatch.setattr(main, "validate_queue_backend", lambda: None)
    monkeypatch.setattr(main, "_check_worker_presence", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "emit_event", lambda *args, **kwargs: (_ for _ in ()).throw(_StopStartup()))


def test_event_bus_guard_raises_in_prod_when_disabled(monkeypatch):
    from AINDY import main

    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "AINDY_REQUIRE_REDIS", True)
    monkeypatch.setenv("AINDY_EVENT_BUS_ENABLED", "false")

    with pytest.raises(RuntimeError, match="AINDY_EVENT_BUS_ENABLED=false"):
        main._enforce_event_bus_startup_guard()


def test_dev_lifespan_allows_local_bringup_without_redis(monkeypatch):
    from AINDY import main

    _patch_minimal_lifespan(monkeypatch, main)
    monkeypatch.setattr(main.settings, "ENV", "development")
    monkeypatch.setattr(main.settings, "REDIS_URL", None)
    monkeypatch.setattr(main.settings, "AINDY_REQUIRE_REDIS", False)
    monkeypatch.setenv("AINDY_EVENT_BUS_ENABLED", "false")

    with pytest.raises(_StopStartup):
        asyncio.run(main.lifespan(main.app).__aenter__())


def test_worker_main_fails_cleanly_when_schema_not_ready(monkeypatch):
    from AINDY.worker import __main__ as worker_main

    monkeypatch.setattr(worker_main.settings, "EXECUTION_MODE", "distributed")
    monkeypatch.setattr(worker_main, "load_plugins", lambda: None)
    monkeypatch.setattr(worker_main, "validate_queue_backend", lambda: None)
    monkeypatch.setattr(worker_main, "start_health_server", lambda: None)
    monkeypatch.setattr(worker_main, "_wait_for_background_schema", lambda: False)
    monkeypatch.setattr(worker_main, "run_worker_loop", MagicMock())

    with pytest.raises(RuntimeError, match="schema is not ready"):
        worker_main.main()


def test_worker_main_rejects_thread_mode(monkeypatch):
    from AINDY.worker import __main__ as worker_main

    monkeypatch.setattr(worker_main.settings, "EXECUTION_MODE", "thread")
    monkeypatch.setattr(worker_main, "load_plugins", lambda: None)
    monkeypatch.setattr(worker_main, "start_health_server", lambda: None)

    with pytest.raises(RuntimeError, match="EXECUTION_MODE=distributed"):
        worker_main.main()

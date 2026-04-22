from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _StopStartup(Exception):
    pass


def _patch_startup_prereqs(monkeypatch, main):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("AINDY_ENFORCE_SCHEMA", "false")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "SECRET_KEY", "schema-guard-test-secret-key-32chars")
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "memory")
    monkeypatch.setattr(main, "_enforce_redis_startup_guard", lambda: None)
    monkeypatch.setattr(main.FastAPICache, "init", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "ensure_mongo_ready", lambda **kwargs: None)
    monkeypatch.setattr(main, "validate_queue_backend", lambda: None)


def test_enforce_schema_false_in_prod_raises(monkeypatch):
    from AINDY import main

    _patch_startup_prereqs(monkeypatch, main)
    monkeypatch.setattr(main.settings, "ENV", "production")

    with pytest.raises(RuntimeError, match="not permitted in production"):
        asyncio.run(main.lifespan(main.app).__aenter__())


def test_enforce_schema_false_in_dev_warns(monkeypatch, caplog):
    from AINDY import main

    _patch_startup_prereqs(monkeypatch, main)
    monkeypatch.setattr(main.settings, "ENV", "staging")
    monkeypatch.setattr(main, "emit_event", lambda *args, **kwargs: (_ for _ in ()).throw(_StopStartup()))

    with pytest.raises(_StopStartup):
        asyncio.run(main.lifespan(main.app).__aenter__())

    assert "Schema enforcement is DISABLED" in caplog.text

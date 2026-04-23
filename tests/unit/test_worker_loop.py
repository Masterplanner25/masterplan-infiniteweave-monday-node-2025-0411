from __future__ import annotations

import threading
from types import ModuleType
from unittest.mock import MagicMock

from AINDY.worker import worker_loop


def test_heartbeat_function_noops_when_backend_has_no_redis():
    worker_loop.reset_worker_state()
    backend = object()
    error_holder: list[Exception] = []
    worker_loop._STOP.set()

    def _target():
        try:
            worker_loop._run_heartbeat(backend)
        except Exception as exc:  # pragma: no cover - defensive capture
            error_holder.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=2)

    assert error_holder == []
    worker_loop.reset_worker_state()


def test_check_worker_presence_warns_when_no_heartbeat(monkeypatch):
    from AINDY import main

    client = MagicMock()
    client.get.return_value = None
    redis_mod = ModuleType("redis")
    redis_mod.from_url = MagicMock(return_value=client)
    logger = MagicMock()

    monkeypatch.setattr(main.settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setitem(__import__("sys").modules, "redis", redis_mod)

    main._check_worker_presence(logger)

    logger.warning.assert_called()
    assert "no worker heartbeat" in logger.warning.call_args[0][0].lower()


def test_stale_recovery_runs_immediate_startup_scan_and_exits_promptly(monkeypatch):
    worker_loop.reset_worker_state()
    logger = MagicMock()
    calls: list[int] = []

    class _Backend:
        def requeue_stale_jobs(self, visibility_timeout):
            calls.append(visibility_timeout)
            worker_loop._STOP.set()
            return 2

    monkeypatch.setattr(worker_loop, "logger", logger)
    monkeypatch.setattr(worker_loop.time, "sleep", lambda _seconds: None)

    worker_loop._run_stale_recovery(
        _Backend(),
        visibility_timeout=45,
        check_interval=5,
    )

    assert calls == [45]
    logger.info.assert_called_once()
    assert "stale recovery" in logger.info.call_args[0][0].lower()
    worker_loop.reset_worker_state()

from __future__ import annotations

import importlib
import json
import os
import socket
import time
from urllib.error import HTTPError
from urllib.request import urlopen


def _read_json(url: str):
    with urlopen(url, timeout=2) as response:
        return response.status, json.loads(response.read().decode())


def test_worker_health_server_reports_liveness_and_readiness(monkeypatch):
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    monkeypatch.setenv("WORKER_HEALTH_PORT", str(port))

    from AINDY.worker import health_server

    health_server = importlib.reload(health_server)
    health_server._worker_ready.clear()

    thread = health_server.start_health_server()
    time.sleep(0.05)

    status, body = _read_json(f"http://127.0.0.1:{port}/healthz")
    assert status == 200
    assert body == {"status": "ok", "worker": "alive"}

    try:
        _read_json(f"http://127.0.0.1:{port}/readyz")
        raise AssertionError("expected /readyz to return 503 before readiness")
    except HTTPError as exc:
        assert exc.code == 503
        body = json.loads(exc.read().decode())
        assert body == {"status": "starting", "worker": "not_ready"}

    health_server.mark_worker_ready()

    status, body = _read_json(f"http://127.0.0.1:{port}/readyz")
    assert status == 200
    assert body == {"status": "ok", "worker": "ready"}
    assert thread.daemon is True

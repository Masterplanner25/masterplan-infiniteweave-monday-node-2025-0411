from __future__ import annotations

import json
import socket
import time
from urllib.error import HTTPError
from urllib.request import urlopen

from AINDY.config import settings
from AINDY.worker import worker_loop


def _read_json(url: str):
    with urlopen(url, timeout=2) as response:
        return response.status, json.loads(response.read().decode())


def test_healthz_returns_200_when_heartbeat_is_fresh():
    worker_loop.reset_worker_state()
    worker_loop._record_worker_heartbeat()

    from AINDY.worker import health_server

    status, body = health_server._healthz_payload()

    assert status == 200
    assert body["status"] == "ok"
    assert "uptime_seconds" in body


def test_healthz_returns_503_when_heartbeat_is_stale(monkeypatch):
    worker_loop.reset_worker_state()
    with worker_loop._HEALTH_LOCK:
        worker_loop._WORKER_HEALTH.last_heartbeat_monotonic = 0.0
        worker_loop._WORKER_HEALTH.started_at_monotonic = 0.0

    monkeypatch.setattr("AINDY.worker.health_server.time.monotonic", lambda: 120.0)
    monkeypatch.setattr(settings, "AINDY_WORKER_LIVENESS_TIMEOUT_SECONDS", 60)

    from AINDY.worker import health_server

    status, body = health_server._healthz_payload()

    assert status == 503
    assert body["status"] == "unavailable"
    assert body["reason"] == "heartbeat_stale"


def test_readyz_returns_200_when_state_is_ready():
    worker_loop.reset_worker_state()
    worker_loop._set_worker_state("READY")
    with worker_loop._HEALTH_LOCK:
        worker_loop._WORKER_HEALTH.first_iteration_complete = True
        worker_loop._WORKER_HEALTH.queue_depth = 1
        worker_loop._WORKER_HEALTH.active_jobs = 2

    from AINDY.worker import health_server

    status, body = health_server._readyz_payload()

    assert status == 200
    assert body == {"status": "ready", "queue_depth": 1, "active_jobs": 2}


def test_readyz_returns_503_with_starting_reason():
    worker_loop.reset_worker_state()

    from AINDY.worker import health_server

    status, body = health_server._readyz_payload()

    assert status == 503
    assert body["status"] == "not_ready"
    assert body["reason"] == "starting"


def test_readyz_returns_503_with_draining_reason():
    worker_loop.reset_worker_state()
    worker_loop._set_worker_state("DRAINING")
    with worker_loop._HEALTH_LOCK:
        worker_loop._WORKER_HEALTH.first_iteration_complete = True

    from AINDY.worker import health_server

    status, body = health_server._readyz_payload()

    assert status == 503
    assert body["status"] == "not_ready"
    assert body["reason"] == "draining"


def test_readyz_returns_503_with_queue_full_reason():
    worker_loop.reset_worker_state()
    worker_loop._set_worker_state("READY")
    with worker_loop._HEALTH_LOCK:
        worker_loop._WORKER_HEALTH.first_iteration_complete = True
        worker_loop._WORKER_HEALTH.queue_depth = 10
        worker_loop._WORKER_HEALTH.queue_capacity = 10

    from AINDY.worker import health_server

    status, body = health_server._readyz_payload()

    assert status == 503
    assert body["status"] == "not_ready"
    assert body["reason"] == "queue_full"


def test_health_server_port_reads_from_config(monkeypatch):
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    monkeypatch.setattr(settings, "AINDY_WORKER_HEALTH_PORT", port)
    worker_loop.reset_worker_state()
    worker_loop._record_worker_heartbeat()

    from AINDY.worker import health_server

    thread = health_server.start_health_server()
    time.sleep(0.05)

    status, body = _read_json(f"http://127.0.0.1:{port}/healthz")

    assert status == 200
    assert body["status"] == "ok"
    assert thread.daemon is True

"""
Minimal HTTP health server for AINDY worker processes.

Includes the legacy worker-loop health endpoints plus a generic
``WorkerHealthServer`` that standalone background workers can embed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

logger = logging.getLogger(__name__)


class WorkerHealthServer:
    """
    Serve GET /health on a background thread.

    Registered checks must all return truthy for the process to be healthy.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8001) -> None:
        self._host = host
        self._port = port
        self._checks: dict[str, Callable[[], bool]] = {}
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def register_check(self, name: str, fn: Callable[[], bool]) -> None:
        self._checks[name] = fn

    def start(self) -> None:
        if self._server is not None:
            return
        checks = self._checks

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/health":
                    self.send_response(404)
                    self.end_headers()
                    return

                results: dict[str, dict[str, object]] = {}
                all_ok = True
                for check_name, check_fn in checks.items():
                    try:
                        ok = bool(check_fn())
                        results[check_name] = {"ok": ok}
                        if not ok:
                            all_ok = False
                    except Exception as exc:
                        results[check_name] = {"ok": False, "error": str(exc)}
                        all_ok = False

                status = 200 if all_ok else 503
                body = json.dumps(
                    {
                        "status": "healthy" if all_ok else "unhealthy",
                        "checks": results,
                    }
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args) -> None:
                pass

        self._server = HTTPServer((self._host, self._port), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"worker-health-{self._port}",
        )
        self._thread.start()
        logger.info(
            "[health] Worker health server listening on %s:%d",
            self._host,
            self._port,
        )

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


def _healthz_payload() -> tuple[int, dict]:
    from AINDY.config import settings
    from AINDY.worker.worker_loop import get_worker_health_snapshot

    snapshot = get_worker_health_snapshot()
    heartbeat_age = float(snapshot["heartbeat_age_seconds"])
    timeout_seconds = int(settings.AINDY_WORKER_LIVENESS_TIMEOUT_SECONDS)
    if heartbeat_age > timeout_seconds:
        return 503, {
            "status": "unavailable",
            "reason": "heartbeat_stale",
            "uptime_seconds": round(float(snapshot["uptime_seconds"]), 3),
            "heartbeat_age_seconds": round(heartbeat_age, 3),
        }
    return 200, {
        "status": "ok",
        "uptime_seconds": round(float(snapshot["uptime_seconds"]), 3),
    }


def _readyz_payload() -> tuple[int, dict]:
    from AINDY.worker.worker_loop import get_worker_health_snapshot

    snapshot = get_worker_health_snapshot()
    state = str(snapshot["state"])
    queue_depth = int(snapshot["queue_depth"])
    queue_capacity = int(snapshot["queue_capacity"])
    active_jobs = int(snapshot["active_jobs"])

    if state == "STARTING" or not bool(snapshot["first_iteration_complete"]):
        return 503, {
            "status": "not_ready",
            "reason": "starting",
            "queue_depth": queue_depth,
            "active_jobs": active_jobs,
        }
    if state == "DRAINING":
        return 503, {
            "status": "not_ready",
            "reason": "draining",
            "queue_depth": queue_depth,
            "active_jobs": active_jobs,
        }
    if queue_capacity > 0 and queue_depth >= queue_capacity:
        return 503, {
            "status": "not_ready",
            "reason": "queue_full",
            "queue_depth": queue_depth,
            "active_jobs": active_jobs,
        }
    return 200, {
        "status": "ready",
        "queue_depth": queue_depth,
        "active_jobs": active_jobs,
    }


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/healthz", "/"):
            status, body = _healthz_payload()
            self._respond_json(status, body)
        elif self.path == "/readyz":
            status, body = _readyz_payload()
            self._respond_json(status, body)
        elif self.path == "/metrics":
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            from AINDY.platform_layer.metrics import REGISTRY

            payload = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self._respond_json(404, {"error": "not_found"})

    def _respond_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        pass


def mark_worker_ready() -> None:
    from AINDY.worker.worker_loop import _set_worker_state

    _set_worker_state("READY")


def start_health_server() -> threading.Thread:
    """Start the legacy worker_loop health server in a background daemon thread."""

    def _serve() -> None:
        from AINDY.config import settings

        port = int(settings.AINDY_WORKER_HEALTH_PORT)
        try:
            server = HTTPServer(("0.0.0.0", port), _HealthHandler)
            logger.info(
                "[Worker] Health server listening on :%d  GET /healthz  GET /readyz  GET /metrics",
                port,
            )
            server.serve_forever()
        except OSError as exc:
            logger.warning(
                "[Worker] Health server could not start on port %d: %s. "
                "Worker probes will not work for this process.",
                port,
                exc,
            )

    thread = threading.Thread(target=_serve, daemon=True, name="aindy-worker-health")
    thread.start()
    return thread

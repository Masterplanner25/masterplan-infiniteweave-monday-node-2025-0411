"""
Minimal HTTP health server for the AINDY worker process.

Runs in a daemon thread. Exposes:
  GET /healthz -> worker liveness based on heartbeat freshness
  GET /readyz  -> worker readiness based on startup/drain/queue state
  GET /metrics -> Prometheus metrics
  GET /        -> alias for /healthz

Uses stdlib http.server only - zero extra framework dependencies.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from AINDY.config import settings
from AINDY.platform_layer.metrics import REGISTRY

logger = logging.getLogger(__name__)


def _healthz_payload() -> tuple[int, dict]:
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
    """Start the health server in a background daemon thread."""

    def _serve() -> None:
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

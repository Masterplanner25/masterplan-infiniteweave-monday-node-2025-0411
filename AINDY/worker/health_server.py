"""
Minimal HTTP liveness server for the AINDY worker process.

Runs in a daemon thread. Exposes:
  GET /healthz  -> 200 {"status": "ok", "worker": "alive"}
  GET /readyz   -> 200 if worker is processing or 503 if not started yet
  GET /         -> 200 {"status": "ok"}  (convenience alias)

Uses stdlib http.server only - zero extra dependencies.
Port is configured via WORKER_HEALTH_PORT (default: 8001).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

WORKER_HEALTH_PORT = int(os.getenv("WORKER_HEALTH_PORT", "8001"))

_worker_ready = threading.Event()


def mark_worker_ready() -> None:
    """Call this once the worker has started its dequeue loop."""
    _worker_ready.set()


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/healthz", "/"):
            self._respond(200, {"status": "ok", "worker": "alive"})
        elif self.path == "/readyz":
            if _worker_ready.is_set():
                self._respond(200, {"status": "ok", "worker": "ready"})
            else:
                self._respond(503, {"status": "starting", "worker": "not_ready"})
        else:
            self._respond(404, {"error": "not_found"})

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        pass


def start_health_server() -> threading.Thread:
    """Start the health server in a background daemon thread."""

    def _serve() -> None:
        port = int(os.getenv("WORKER_HEALTH_PORT", str(WORKER_HEALTH_PORT)))
        try:
            server = HTTPServer(("0.0.0.0", port), _HealthHandler)
            logger.info(
                "[Worker] Health server listening on :%d  GET /healthz  GET /readyz",
                port,
            )
            server.serve_forever()
        except OSError as exc:
            logger.warning(
                "[Worker] Health server could not start on port %d: %s. "
                "Liveness probes will not work for this process.",
                port,
                exc,
            )

    thread = threading.Thread(target=_serve, daemon=True, name="aindy-worker-health")
    thread.start()
    return thread

"""Standalone request metric writer worker process."""
from __future__ import annotations

import logging
import os
import signal
import time

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def main() -> None:
    from AINDY.platform_layer.log_config import configure_logging

    configure_logging(
        env=os.getenv("ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

    from AINDY.core.request_metric_writer import get_writer
    from AINDY.worker.health_server import WorkerHealthServer

    health_port = int(os.getenv("WORKER_HEALTH_PORT", "8003"))
    health = WorkerHealthServer(port=health_port)

    writer = get_writer()
    is_running = True

    def _check_alive() -> bool:
        snapshot = writer.snapshot()
        return bool(snapshot.get("worker_running", False))

    health.register_check("writer_alive", _check_alive)
    health.start()

    def _shutdown(signum, frame) -> None:  # type: ignore[unused-argument]
        nonlocal is_running
        is_running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("[metric_writer_worker] Starting request metric writer")
    writer.start()

    try:
        while is_running:
            time.sleep(1)
    finally:
        logger.info("[metric_writer_worker] Stopping request metric writer")
        writer.stop(timeout=10)
        health.stop()
        logger.info("[metric_writer_worker] Shutdown complete")


if __name__ == "__main__":
    main()

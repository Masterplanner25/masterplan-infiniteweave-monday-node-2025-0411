"""Standalone memory ingest worker process."""
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

    from AINDY.db.database import SessionLocal  # noqa: F401
    from AINDY.memory.memory_ingest_service import configure_memory_ingest_queue
    from AINDY.worker.health_server import WorkerHealthServer

    health_port = int(os.getenv("WORKER_HEALTH_PORT", "8002"))
    health = WorkerHealthServer(port=health_port)

    queue = configure_memory_ingest_queue()
    is_running = True

    def _check_alive() -> bool:
        snapshot = queue.snapshot()
        return bool(snapshot.get("worker_running", False))

    health.register_check("queue_alive", _check_alive)
    health.start()

    def _shutdown(signum, frame) -> None:  # type: ignore[unused-argument]
        nonlocal is_running
        logger.info("[memory_ingest_worker] Shutdown signal received")
        is_running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("[memory_ingest_worker] Starting memory ingest queue")
    queue.start()

    try:
        while is_running:
            time.sleep(1)
    finally:
        logger.info("[memory_ingest_worker] Stopping memory ingest queue")
        queue.stop(timeout=10, drain=True)
        health.stop()
        logger.info("[memory_ingest_worker] Shutdown complete")


if __name__ == "__main__":
    main()

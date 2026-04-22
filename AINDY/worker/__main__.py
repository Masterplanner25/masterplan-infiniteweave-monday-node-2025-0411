"""Production worker entrypoint.

Starts the existing worker lifecycle hooks, then blocks in the distributed
queue consumer. Job execution remains owned by ``worker_loop.process_one_job``.
"""

from __future__ import annotations

import logging
import os
import sys

from AINDY.platform_layer import scheduler_service
from AINDY.platform_layer.registry import load_plugins
from AINDY.worker import _wait_for_background_schema, lifecycle_services
from AINDY.worker.health_server import mark_worker_ready, start_health_server
from AINDY.worker.worker_loop import run_worker_loop

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    load_plugins()
    scheduler_started = False
    lifecycle_started = False

    try:
        start_health_server()
        if _wait_for_background_schema():
            lifecycle_started = lifecycle_services.start_background_tasks(
                enable=True,
                log=logger,
            )
            if lifecycle_started:
                scheduler_service.start()
                scheduler_started = True
                logger.info("Worker started scheduler lifecycle")
            else:
                logger.info("Worker started without scheduler leadership")
        else:
            logger.warning(
                "Worker started before schema was ready; scheduler disabled for this process"
            )

        concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
        mark_worker_ready()
        run_worker_loop(concurrency=concurrency)
    finally:
        if scheduler_started:
            scheduler_service.stop()
        if lifecycle_started:
            lifecycle_services.stop_background_tasks(log=logger)


if __name__ == "__main__":
    main()

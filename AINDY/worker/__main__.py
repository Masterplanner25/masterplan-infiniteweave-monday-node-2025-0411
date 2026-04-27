"""Production worker entrypoint.

Starts the existing worker lifecycle hooks, then blocks in the distributed
queue consumer. Job execution remains owned by ``worker_loop.process_one_job``.
"""

from __future__ import annotations

import logging
import os
import sys

from AINDY.config import settings
from AINDY.core.distributed_queue import validate_queue_backend
from AINDY.platform_layer.deployment_contract import publish_worker_runtime_state
from AINDY.platform_layer import scheduler_service
from AINDY.platform_layer.registry import load_plugins
from AINDY.worker import _wait_for_background_schema, lifecycle_services
from AINDY.worker.worker_loop import run_worker_loop

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    load_plugins()
    publish_worker_runtime_state(
        startup_complete=False,
        queue_ready=False,
        schema_ready=False,
        scheduler_role="disabled",
    )
    scheduler_started = False
    lifecycle_started = False

    try:
        if settings.EXECUTION_MODE != "distributed":
            raise RuntimeError(
                "Worker process requires EXECUTION_MODE=distributed. "
                "Do not run the worker in thread mode."
            )
        validate_queue_backend()
        publish_worker_runtime_state(queue_ready=True)
        schema_ready = _wait_for_background_schema()
        publish_worker_runtime_state(schema_ready=schema_ready)
        if schema_ready:
            lifecycle_started = lifecycle_services.start_background_tasks(
                enable=True,
                log=logger,
            )
            if lifecycle_started:
                scheduler_service.start()
                scheduler_started = True
                publish_worker_runtime_state(scheduler_role="leader")
                logger.info("Worker started scheduler lifecycle")
            else:
                publish_worker_runtime_state(scheduler_role="follower")
                logger.info("Worker started without scheduler leadership")
        else:
            raise RuntimeError(
                "Worker startup blocked: required schema is not ready "
                "(background_task_leases missing). Run migrations before starting the worker."
            )

        concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
        publish_worker_runtime_state(startup_complete=True)
        run_worker_loop(concurrency=concurrency)
    finally:
        publish_worker_runtime_state(startup_complete=False)
        if scheduler_started:
            scheduler_service.stop()
        if lifecycle_started:
            lifecycle_services.stop_background_tasks(log=logger)


if __name__ == "__main__":
    main()

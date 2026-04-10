# Worker package — distributed async job executor.
# The traditional worker entrypoint (schema-ready check + background tasks)
# is defined here so that `import worker` resolves to this package and still
# exposes SessionLocal, _background_schema_ready, main, etc.

import logging
import signal
import time

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from db.database import SessionLocal
from platform_layer import scheduler_service
from domain import task_services

logger = logging.getLogger(__name__)
_RUNNING = True


def _stop(*_args):
    global _RUNNING
    _RUNNING = False


def _background_schema_ready() -> bool:
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        return inspector.has_table("background_task_leases")
    except SQLAlchemyError as exc:
        logger.warning("Worker schema readiness check failed: %s", exc)
        return False
    finally:
        db.close()


def _wait_for_background_schema(timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while _RUNNING and time.time() < deadline:
        if _background_schema_ready():
            return True
        logger.info("Worker waiting for migrated schema: background_task_leases not ready yet")
        time.sleep(2)
    return _background_schema_ready()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    if _wait_for_background_schema():
        is_leader = task_services.start_background_tasks(enable=True, log=logger)
        if is_leader:
            scheduler_service.start()
            logger.info("Worker started as scheduler leader")
        else:
            logger.info("Worker started without scheduler leadership")
    else:
        logger.warning("Worker started before schema was ready; scheduler disabled for this process")

    try:
        while _RUNNING:
            time.sleep(1)
    finally:
        scheduler_service.stop()
        task_services.stop_background_tasks(log=logger)


if __name__ == "__main__":
    main()

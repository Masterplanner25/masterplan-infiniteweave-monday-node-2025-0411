from __future__ import annotations

import threading

from AINDY.kernel.scheduler.core import SchedulerCoreMixin
from AINDY.kernel.scheduler.dispatch import SchedulerDispatchMixin
from AINDY.kernel.scheduler.persistence import SchedulerPersistenceMixin
from AINDY.kernel.scheduler.recovery import SchedulerRecoveryMixin
from AINDY.kernel.scheduler.waits import SchedulerWaitMixin


class SchedulerEngine(
    SchedulerDispatchMixin,
    SchedulerWaitMixin,
    SchedulerPersistenceMixin,
    SchedulerRecoveryMixin,
    SchedulerCoreMixin,
):
    pass


_SCHEDULER: SchedulerEngine | None = None
_SCHED_LOCK = threading.Lock()


def get_scheduler_engine() -> SchedulerEngine:
    global _SCHEDULER
    if _SCHEDULER is None:
        with _SCHED_LOCK:
            if _SCHEDULER is None:
                _SCHEDULER = SchedulerEngine()
    return _SCHEDULER

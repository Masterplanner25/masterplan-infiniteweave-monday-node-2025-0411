"""
Tests that scheduler_service loads the real APScheduler BackgroundScheduler,
not the in-file fallback stub.
"""
import pytest


def test_background_scheduler_is_real_apscheduler():
    """Fails if the wrong (stub) BackgroundScheduler class is loaded."""
    from AINDY.platform_layer.scheduler_service import BackgroundScheduler

    # The real APScheduler BackgroundScheduler lives in apscheduler.schedulers.background
    from apscheduler.schedulers.background import (
        BackgroundScheduler as RealBackgroundScheduler,
    )

    assert BackgroundScheduler is RealBackgroundScheduler, (
        "scheduler_service is using the fallback stub, not the real APScheduler. "
        "Check that apscheduler is installed and the import path is correct."
    )


def test_real_scheduler_get_jobs_returns_list():
    """get_jobs() on the real scheduler returns a list (not a stub list of _FallbackJob)."""
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler()
    jobs = sched.get_jobs()
    assert isinstance(jobs, list)
    # Real APScheduler returns Job objects; stub would return _FallbackJob objects.
    # An empty list is fine — we just verify get_jobs is the real method.
    assert all(
        hasattr(j, "id") and hasattr(j, "next_run_time") for j in jobs
    ), "get_jobs() returned objects missing APScheduler Job attributes"

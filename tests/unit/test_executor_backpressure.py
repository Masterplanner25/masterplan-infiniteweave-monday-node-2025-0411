"""
Tests that submit_async_job() rejects new jobs when the execution queue is full.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_semaphore():
    """Ensure the module-level semaphore is clean before and after each test."""
    from AINDY.platform_layer import async_job_service
    async_job_service._SUBMIT_SEMAPHORE = None
    yield
    async_job_service._SUBMIT_SEMAPHORE = None


def test_submit_async_job_rejects_when_queue_full(monkeypatch):
    """
    With AINDY_ASYNC_QUEUE_MAXSIZE=1 and the semaphore saturated,
    submit_async_job raises RuntimeError containing 'queue full'.
    """
    monkeypatch.setenv("AINDY_ASYNC_QUEUE_MAXSIZE", "1")

    from AINDY.platform_layer import async_job_service

    # Acquire the single available slot to simulate a saturated queue.
    sem = async_job_service._get_semaphore()
    acquired = sem.acquire(blocking=False)
    assert acquired, "Semaphore should be acquirable on a fresh reset"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()

    # Mock settings so that test-mode inline-execution is bypassed and the
    # semaphore check is reached.
    mock_settings = MagicMock()
    mock_settings.is_testing = False
    mock_settings.TEST_MODE = False

    try:
        with (
            patch("AINDY.platform_layer.async_job_service.SessionLocal", return_value=mock_db),
            patch("AINDY.platform_layer.async_job_service.settings", mock_settings),
            patch("AINDY.platform_layer.async_job_service._is_background_runner_active", return_value=True),
            patch("AINDY.platform_layer.async_job_service._session_dialect_name", return_value="postgresql"),
            patch("AINDY.platform_layer.async_job_service._emit_async_system_event"),
            patch("AINDY.platform_layer.async_job_service.emit_error_event"),
            patch("AINDY.platform_layer.async_job_service.parse_user_id", return_value=None),
            # Clear PYTEST_CURRENT_TEST so force_inline_env resolves to False.
            # Enable background tasks so runner_disabled resolves to False.
            patch.dict(os.environ, {
                "ENV": "production",
                "PYTEST_CURRENT_TEST": "",
                "AINDY_ENABLE_BACKGROUND_TASKS": "true",
            }),
        ):
            with pytest.raises(RuntimeError, match="queue full"):
                async_job_service.submit_async_job(
                    task_name="test_task",
                    payload={"x": 1},
                    user_id=None,
                    source="test",
                )
    finally:
        sem.release()

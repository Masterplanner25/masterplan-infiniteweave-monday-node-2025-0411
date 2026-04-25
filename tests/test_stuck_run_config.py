from __future__ import annotations

import pytest


def test_stuck_run_threshold_uses_settings():
    """_default_threshold_minutes must read from settings, not raw env."""
    from AINDY.config import settings
    from AINDY.agents.stuck_run_service import _default_threshold_minutes

    assert _default_threshold_minutes() == settings.STUCK_RUN_THRESHOLD_MINUTES


def test_threshold_greater_than_wait_timeout():
    """Stuck-run threshold must exceed flow wait timeout."""
    from AINDY.config import settings

    assert settings.STUCK_RUN_THRESHOLD_MINUTES > settings.FLOW_WAIT_TIMEOUT_MINUTES, (
        f"STUCK_RUN_THRESHOLD_MINUTES={settings.STUCK_RUN_THRESHOLD_MINUTES} "
        f"must exceed FLOW_WAIT_TIMEOUT_MINUTES={settings.FLOW_WAIT_TIMEOUT_MINUTES}"
    )


def test_invalid_threshold_raises_at_settings_init(monkeypatch):
    """Settings must reject threshold <= wait timeout."""
    from AINDY.config import Settings

    monkeypatch.setenv("STUCK_RUN_THRESHOLD_MINUTES", "20")
    monkeypatch.setenv("FLOW_WAIT_TIMEOUT_MINUTES", "30")

    with pytest.raises(Exception):
        Settings()


def test_default_threshold_not_ten():
    """The old hardcoded default of 10 minutes must no longer exist."""
    from AINDY.config import settings

    assert settings.STUCK_RUN_THRESHOLD_MINUTES != 10, (
        "Default threshold is still 10 minutes — the config was not updated."
    )

from __future__ import annotations

import pytest


def _make_settings(*, flow_wait_timeout_minutes: int, stuck_run_threshold_minutes: int):
    from AINDY.config import Settings

    return Settings(
        DATABASE_URL="sqlite:///:memory:",
        OPENAI_API_KEY="test-openai-key",
        ENV="test",
        TEST_MODE=True,
        FLOW_WAIT_TIMEOUT_MINUTES=flow_wait_timeout_minutes,
        STUCK_RUN_THRESHOLD_MINUTES=stuck_run_threshold_minutes,
    )


@pytest.mark.parametrize("threshold", [29, 30])
def test_rejects_stuck_run_threshold_not_greater_than_wait_timeout(threshold: int):
    with pytest.raises(
        ValueError,
        match=(
            rf"STUCK_RUN_THRESHOLD_MINUTES \({threshold}\) "
            r"must be greater than FLOW_WAIT_TIMEOUT_MINUTES \(30\)\. "
            r"Legitimately waiting flows would be incorrectly recovered\."
        ),
    ):
        _make_settings(
            flow_wait_timeout_minutes=30,
            stuck_run_threshold_minutes=threshold,
        )


@pytest.mark.parametrize(
    ("timeout", "threshold"),
    [
        (30, 31),
        (30, 45),
    ],
)
def test_accepts_stuck_run_threshold_greater_than_wait_timeout(
    timeout: int,
    threshold: int,
):
    settings = _make_settings(
        flow_wait_timeout_minutes=timeout,
        stuck_run_threshold_minutes=threshold,
    )

    assert settings.FLOW_WAIT_TIMEOUT_MINUTES == timeout
    assert settings.STUCK_RUN_THRESHOLD_MINUTES == threshold

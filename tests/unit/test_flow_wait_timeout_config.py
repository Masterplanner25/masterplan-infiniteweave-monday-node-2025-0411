from __future__ import annotations

from datetime import datetime, timezone


def test_default_wait_deadline_uses_override_60_minutes():
    from AINDY.runtime.flow_engine.shared import _default_wait_deadline

    now = datetime.now(timezone.utc)
    deadline = _default_wait_deadline(timeout_minutes=60)
    delta_minutes = (deadline - now).total_seconds() / 60

    assert 59 <= delta_minutes <= 61


def test_default_wait_deadline_uses_global_setting_when_override_none(monkeypatch):
    from AINDY.runtime.flow_engine import shared

    monkeypatch.setattr(shared.settings, "FLOW_WAIT_TIMEOUT_MINUTES", 45)

    now = datetime.now(timezone.utc)
    deadline = shared._default_wait_deadline(timeout_minutes=None)
    delta_minutes = (deadline - now).total_seconds() / 60

    assert 44 <= delta_minutes <= 46


def test_get_flow_wait_timeout_reads_registered_override(monkeypatch):
    from AINDY.runtime.flow_engine import runner_steps

    monkeypatch.setitem(
        runner_steps.FLOW_REGISTRY,
        "test_wait_flow",
        {
            "start": "node_a",
            "edges": {},
            "end": ["node_a"],
            "wait_timeout_minutes": 120,
        },
    )

    assert runner_steps._get_flow_wait_timeout("test_wait_flow") == 120

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize(
    ("module_path", "func_name", "args", "dispatch_result", "expected"),
    [
        (
            "apps.tasks.services.analytics_bridge",
            "get_kpi_snapshot_via_syscall",
            ("user-1", object()),
            {"status": "success", "data": {"master_score": 88.0, "execution_speed": 72.0}},
            {"master_score": 88.0, "execution_speed": 72.0},
        ),
        (
            "apps.tasks.services.masterplan_bridge",
            "get_eta_via_syscall",
            ("42", "user-1", object()),
            {"status": "success", "data": {"eta": {"projected_completion_date": "2026-05-01"}}},
            {"projected_completion_date": "2026-05-01"},
        ),
        (
            "apps.tasks.services.masterplan_bridge",
            "get_active_masterplan_via_syscall",
            ("user-1", object()),
            {"status": "success", "data": {"masterplan": {"id": 42, "anchor_date": "2026-05-01T00:00:00"}}},
            {"id": 42, "anchor_date": "2026-05-01T00:00:00"},
        ),
        (
            "apps.analytics.services.tasks_bridge",
            "get_task_graph_context_via_syscall",
            ("user-1", object()),
            {"status": "success", "data": {"nodes": {"1": {"name": "A"}}, "ready": [1]}},
            {"nodes": {"1": {"name": "A"}}, "ready": [1]},
        ),
    ],
)
def test_bridge_returns_expected_shape(module_path, func_name, args, dispatch_result, expected):
    module = __import__(module_path, fromlist=[func_name])
    fn = getattr(module, func_name)
    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = dispatch_result

    with patch("AINDY.kernel.syscall_dispatcher.get_dispatcher", return_value=dispatcher):
        assert fn(*args) == expected


@pytest.mark.parametrize(
    ("module_path", "func_name", "args"),
    [
        ("apps.tasks.services.analytics_bridge", "get_kpi_snapshot_via_syscall", ("user-1", object())),
        ("apps.tasks.services.masterplan_bridge", "get_eta_via_syscall", ("42", "user-1", object())),
        ("apps.tasks.services.masterplan_bridge", "get_active_masterplan_via_syscall", ("user-1", object())),
        ("apps.analytics.services.tasks_bridge", "get_task_graph_context_via_syscall", ("user-1", object())),
    ],
)
def test_bridge_raises_503_when_dispatcher_raises(module_path, func_name, args):
    module = __import__(module_path, fromlist=[func_name])
    fn = getattr(module, func_name)
    dispatcher = MagicMock()
    dispatcher.dispatch.side_effect = RuntimeError("dispatcher offline")

    with patch("AINDY.kernel.syscall_dispatcher.get_dispatcher", return_value=dispatcher):
        with pytest.raises(HTTPException) as exc_info:
            fn(*args)

    assert exc_info.value.status_code == 503


def test_assert_masterplan_owned_bridge_raises_value_error_on_missing_plan():
    from apps.tasks.services.masterplan_bridge import assert_masterplan_owned_via_syscall

    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = {"status": "error", "error": "NOT_FOUND:MasterPlan not found"}

    with patch("AINDY.kernel.syscall_dispatcher.get_dispatcher", return_value=dispatcher):
        with pytest.raises(ValueError) as exc_info:
            assert_masterplan_owned_via_syscall("42", "user-1", object())

    assert str(exc_info.value) == "masterplan_not_found:42"

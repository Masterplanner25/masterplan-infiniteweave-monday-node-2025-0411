from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher
from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY


def _ctx(*, capability: str, db) -> SyscallContext:
    return SyscallContext(
        execution_unit_id="eu-test",
        user_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        capabilities=[capability],
        trace_id="trace-test",
        metadata={"_db": db},
    )


class TestTaskDomainSyscalls:
    def test_register_task_syscall_handlers_registers_names(self):
        from apps.tasks.syscalls.syscall_handlers import register_task_syscall_handlers

        register_task_syscall_handlers()

        assert "sys.v1.task.get" in SYSCALL_REGISTRY
        assert "sys.v1.task.queue_automation" in SYSCALL_REGISTRY
        assert "sys.v1.task.get_user_tasks" in SYSCALL_REGISTRY
        assert "sys.v1.task.count" in SYSCALL_REGISTRY
        assert "sys.v1.task.count_completed_since" in SYSCALL_REGISTRY
        assert "sys.v1.task.list_for_masterplan" in SYSCALL_REGISTRY
        assert "sys.v1.task.delete_by_ids" in SYSCALL_REGISTRY

    def test_dispatch_task_get_returns_envelope(self):
        from apps.tasks.syscalls.syscall_handlers import register_task_syscall_handlers

        register_task_syscall_handlers()
        mock_db = MagicMock()
        mock_task = SimpleNamespace(
            id=42,
            name="Draft spec",
            status="pending",
            priority="high",
            masterplan_id=7,
            automation_type="notify",
            automation_config={"channel": "email"},
            end_time=None,
        )
        mock_svc = ModuleType("apps.tasks.services.task_service")
        mock_svc.get_task_by_id = MagicMock(return_value=mock_task)

        with patch.dict(sys.modules, {"apps.tasks.services.task_service": mock_svc}):
            result = get_dispatcher().dispatch(
                "sys.v1.task.get",
                {"task_id": 42},
                _ctx(capability="task.read", db=mock_db),
            )

        assert result["status"] == "success"
        assert result["syscall"] == "sys.v1.task.get"
        assert result["data"]["task"]["id"] == "42"
        assert result["data"]["task"]["automation_type"] == "notify"

    def test_dispatch_task_queue_automation_returns_expected_payload(self):
        from apps.tasks.syscalls.syscall_handlers import register_task_syscall_handlers

        register_task_syscall_handlers()
        mock_db = MagicMock()
        mock_task = SimpleNamespace(
            id=42,
            name="Draft spec",
            status="pending",
            priority="high",
            masterplan_id=7,
            automation_type="notify",
            automation_config={"channel": "email"},
        )
        dispatch_payload = {"job_id": "job-1", "accepted": True}
        mock_svc = ModuleType("apps.tasks.services.task_service")
        mock_svc.get_task_by_id = MagicMock(return_value=mock_task)
        mock_svc.queue_task_automation = MagicMock(return_value=dispatch_payload)

        with patch.dict(sys.modules, {"apps.tasks.services.task_service": mock_svc}):
            result = get_dispatcher().dispatch(
                "sys.v1.task.queue_automation",
                {"task_id": 42, "automation_type": "notify"},
                _ctx(capability="task.write", db=mock_db),
            )

        assert result["status"] == "success"
        assert result["data"]["automation_task_trigger_result"] == dispatch_payload
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_task)

    def test_dispatch_task_get_user_tasks_returns_minimal_snapshot(self):
        from apps.tasks.syscalls.syscall_handlers import register_task_syscall_handlers

        register_task_syscall_handlers()
        mock_db = MagicMock()
        query = mock_db.query.return_value
        query.filter.return_value.all.return_value = [
            SimpleNamespace(status="completed", end_time=datetime(2026, 1, 2, tzinfo=timezone.utc)),
            SimpleNamespace(status="pending", end_time=None),
        ]

        mock_svc = ModuleType("apps.tasks.services.task_service")
        mock_svc._user_uuid = MagicMock(return_value=uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"))
        mock_models = ModuleType("apps.tasks.models")
        mock_models.Task = type("Task", (), {"user_id": object()})

        with patch.dict(
            sys.modules,
            {
                "apps.tasks.services.task_service": mock_svc,
                "apps.tasks.models": mock_models,
            },
        ):
            result = get_dispatcher().dispatch(
                "sys.v1.task.get_user_tasks",
                {},
                _ctx(capability="task.read", db=mock_db),
            )

        assert result["status"] == "success"
        assert result["data"]["tasks"] == [
            {"status": "completed", "end_time": "2026-01-02T00:00:00+00:00"},
            {"status": "pending", "end_time": None},
        ]

    def test_dispatch_runtime_masterplan_helper_task_syscalls(self):
        from apps.tasks.syscalls.syscall_handlers import register_task_syscall_handlers

        register_task_syscall_handlers()
        mock_db = MagicMock()
        mock_public = ModuleType("apps.tasks.services.public_surface_service")
        mock_public.count_tasks = MagicMock(return_value=3)
        mock_public.count_tasks_completed_since = MagicMock(return_value=2)
        mock_public.list_tasks_for_masterplan = MagicMock(
            return_value=[
                SimpleNamespace(id=1, name="Task 1", status="pending"),
                SimpleNamespace(id=2, name="Task 2", status="completed"),
            ]
        )
        mock_public.delete_tasks_by_ids = MagicMock(return_value=2)
        mock_public.task_to_dict = MagicMock(
            side_effect=lambda task: {"id": task.id, "name": task.name, "status": task.status}
        )

        with patch.dict(sys.modules, {"apps.tasks.services.public_surface_service": mock_public}):
            count_result = get_dispatcher().dispatch(
                "sys.v1.task.count",
                {"masterplan_id": 7},
                _ctx(capability="task.read", db=mock_db),
            )
            completed_result = get_dispatcher().dispatch(
                "sys.v1.task.count_completed_since",
                {"since": "2026-01-01T00:00:00+00:00"},
                _ctx(capability="task.read", db=mock_db),
            )
            list_result = get_dispatcher().dispatch(
                "sys.v1.task.list_for_masterplan",
                {"masterplan_id": 7},
                _ctx(capability="task.read", db=mock_db),
            )
            delete_result = get_dispatcher().dispatch(
                "sys.v1.task.delete_by_ids",
                {"task_ids": [1, 2]},
                _ctx(capability="task.write", db=mock_db),
            )

        assert count_result["status"] == "success"
        assert count_result["data"]["count"] == 3
        assert completed_result["status"] == "success"
        assert completed_result["data"]["count"] == 2
        assert list_result["status"] == "success"
        assert list_result["data"]["tasks"] == [
            {"id": 1, "name": "Task 1", "status": "pending"},
            {"id": 2, "name": "Task 2", "status": "completed"},
        ]
        assert delete_result["status"] == "success"
        assert delete_result["data"]["deleted_count"] == 2

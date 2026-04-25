"""Verify task syscalls are registered by the canonical source only."""
from __future__ import annotations

import logging
import pathlib

from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY, SyscallEntry


EXPECTED_TASK_SYSCALLS = [
    "sys.v1.task.create",
    "sys.v1.task.complete",
    "sys.v1.task.complete_full",
    "sys.v1.task.start",
    "sys.v1.task.pause",
    "sys.v1.task.orchestrate",
    "sys.v1.task.get",
    "sys.v1.task.queue_automation",
    "sys.v1.task.get_user_tasks",
    "sys.v1.tasks.get_graph_context",
    "sys.v1.watcher.ingest",
]


def test_task_syscalls_registered_after_bootstrap(client):
    """All expected task syscalls must be present in the registry after boot."""
    missing = [name for name in EXPECTED_TASK_SYSCALLS if name not in SYSCALL_REGISTRY]
    assert missing == [], f"Task syscalls not registered after bootstrap: {missing}"


def test_no_automation_import_of_task_registration():
    """Automation module must not import register_task_syscall_handlers."""
    source = pathlib.Path("apps/automation/syscalls/syscall_handlers.py").read_text(
        encoding="utf-8"
    )
    assert "register_task_syscall_handlers" not in source, (
        "apps/automation/syscalls/syscall_handlers.py imports "
        "register_task_syscall_handlers from apps.tasks — this is a "
        "cross-domain registration that belongs exclusively in "
        "apps/tasks/bootstrap.py"
    )


def test_registry_warns_on_duplicate_registration(caplog):
    """Re-registering a syscall with a different handler logs a warning."""

    def handler_a(payload, context):
        return {}

    def handler_b(payload, context):
        return {}

    probe_name = "sys.v1.test.duplicate_probe"
    SYSCALL_REGISTRY[probe_name] = SyscallEntry(handler_a, capability="test")
    with caplog.at_level(logging.WARNING, logger="AINDY.kernel.syscall_registry"):
        SYSCALL_REGISTRY[probe_name] = SyscallEntry(handler_b, capability="test")

    assert any("re-registered" in record.message for record in caplog.records), (
        "Expected a warning when re-registering with a different handler"
    )

    del SYSCALL_REGISTRY[probe_name]

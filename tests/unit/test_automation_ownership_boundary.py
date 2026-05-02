from __future__ import annotations

from pathlib import Path


def test_task_syscalls_register_from_tasks_domain_and_watcher_ingest_from_automation():
    from AINDY.kernel.syscall_handlers import register_all_domain_handlers
    from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY

    register_all_domain_handlers()

    assert SYSCALL_REGISTRY["sys.v1.task.create"].handler.__module__ == (
        "apps.tasks.syscalls.syscall_handlers"
    )
    assert SYSCALL_REGISTRY["sys.v1.watcher.ingest"].handler.__module__ == (
        "apps.automation.syscalls.syscall_handlers"
    )


def test_moved_watcher_flows_register_and_automation_flows_remain_available():
    from AINDY.platform_layer import registry
    import apps.automation.bootstrap as automation_bootstrap
    from AINDY.runtime.flow_engine import FLOW_REGISTRY

    automation_bootstrap._register_flows()
    for register_fn in tuple(registry._flows):
        register_fn()

    assert FLOW_REGISTRY["watcher_signals_receive"]["start"] == "watcher_ingest_validate"
    assert FLOW_REGISTRY["watcher_evaluate_trigger"]["start"] == "watcher_evaluate_trigger_node"


def test_automation_no_longer_imports_watcher_flow_adapter_modules():
    automation_flows_source = Path("apps/automation/flows/automation_flows.py").read_text()
    extended_source = Path("apps/automation/flows/flow_definitions_extended.py").read_text()

    assert "watcher_flows" not in automation_flows_source
    assert "apps.automation.flows.watcher_flows" not in extended_source

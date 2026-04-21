from __future__ import annotations

import importlib


def test_automation_flows_register_all_nodes():
    from AINDY.runtime.flow_engine import NODE_REGISTRY
    from apps.automation.flows import automation_flows

    before_count = len(NODE_REGISTRY)
    automation_flows.register()
    after_count = len(NODE_REGISTRY)

    assert after_count - before_count >= 56 or after_count >= 56


def test_each_group_file_has_register():
    # Platform-wide files that remain in apps/automation/flows/
    automation_files = [
        "apps.automation.flows.memory_flows",
        "apps.automation.flows.flow_engine_flows",
        "apps.automation.flows.automation_system_flows",
        "apps.automation.flows.observability_flows",
        "apps.automation.flows.watcher_flows",
        "apps.automation.flows.dashboard_autonomy_flows",
    ]
    # Domain files migrated to their own apps
    domain_files = [
        "apps.agent.flows.agent_flows",
        "apps.tasks.flows.tasks_flows",
        "apps.masterplan.flows.masterplan_flows",
        "apps.analytics.flows.analytics_flows",
        "apps.arm.flows.arm_flows",
        "apps.search.flows.search_flows",
        "apps.freelance.flows.freelance_flows",
    ]
    for module_path in automation_files + domain_files:
        mod = importlib.import_module(module_path)
        assert callable(getattr(mod, "register", None)), (
            f"{module_path} missing register()"
        )

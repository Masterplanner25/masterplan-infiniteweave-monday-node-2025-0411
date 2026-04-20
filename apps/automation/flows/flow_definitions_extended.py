"""
flow_definitions_extended.py - Hard Execution Boundary node extensions.

Coordinator only. Bootstrap continues importing this module, while the actual
domain-specific node and flow registrations live in per-domain modules.
"""

from apps.automation.flows.arm_flows import *  # noqa: F401,F403
from apps.automation.flows.arm_flows import register as register_arm
from apps.automation.flows.analytics_flows import *  # noqa: F401,F403
from apps.automation.flows.analytics_flows import register as register_analytics
from apps.automation.flows import _flow_registration as _flow_registration
from apps.automation.flows.agent_flows import *  # noqa: F401,F403
from apps.automation.flows import agent_flows as _agent_flows
from apps.automation.flows.memory_flows import *  # noqa: F401,F403
from apps.automation.flows import memory_flows as _memory_flows
from apps.automation.flows.flow_engine_flows import *  # noqa: F401,F403
from apps.automation.flows import flow_engine_flows as _flow_engine_flows
from apps.automation.flows.automation_system_flows import *  # noqa: F401,F403
from apps.automation.flows import automation_system_flows as _automation_system_flows
from apps.automation.flows.observability_flows import *  # noqa: F401,F403
from apps.automation.flows import observability_flows as _observability_flows
from apps.automation.flows.watcher_flows import *  # noqa: F401,F403
from apps.automation.flows import watcher_flows as _watcher_flows
from apps.automation.flows.dashboard_autonomy_flows import *  # noqa: F401,F403
from apps.automation.flows import dashboard_autonomy_flows as _dashboard_autonomy_flows
from apps.automation.flows import automation_flows as _automation_flows
from apps.automation.flows.automation_flows import register as register_automation
from apps.automation.flows.freelance_flows import *  # noqa: F401,F403
from apps.automation.flows.freelance_flows import register as register_freelance
from apps.automation.flows.masterplan_flows import *  # noqa: F401,F403
from apps.automation.flows.masterplan_flows import register as register_masterplan
from apps.automation.flows.search_flows import *  # noqa: F401,F403
from apps.automation.flows.search_flows import register as register_search
from apps.automation.flows.tasks_flows import *  # noqa: F401,F403
from apps.automation.flows.tasks_flows import register as register_tasks


def register_all() -> None:
    register_arm()
    register_analytics()
    register_tasks()
    register_masterplan()
    register_search()
    register_freelance()
    register_automation()


def register_extended_flows():
    flow_modules = (
        _agent_flows,
        _memory_flows,
        _flow_engine_flows,
        _automation_system_flows,
        _observability_flows,
        _watcher_flows,
        _dashboard_autonomy_flows,
    )
    if "FLOW_REGISTRY" in globals():
        _flow_registration.FLOW_REGISTRY = globals()["FLOW_REGISTRY"]
        _automation_flows.FLOW_REGISTRY = globals()["FLOW_REGISTRY"]
        for module in flow_modules:
            module.FLOW_REGISTRY = globals()["FLOW_REGISTRY"]
    if "register_flow" in globals():
        _flow_registration.register_flow = globals()["register_flow"]
        _automation_flows.register_flow = globals()["register_flow"]
        for module in flow_modules:
            module.register_flow = globals()["register_flow"]
    register_all()

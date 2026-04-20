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
from apps.automation.flows.automation_flows import *  # noqa: F401,F403
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
    if "FLOW_REGISTRY" in globals():
        _flow_registration.FLOW_REGISTRY = globals()["FLOW_REGISTRY"]
        _automation_flows.FLOW_REGISTRY = globals()["FLOW_REGISTRY"]
    if "register_flow" in globals():
        _flow_registration.register_flow = globals()["register_flow"]
        _automation_flows.register_flow = globals()["register_flow"]
    register_all()

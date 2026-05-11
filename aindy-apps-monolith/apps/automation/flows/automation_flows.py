"""
automation_flows.py - thin delegator.

Node implementations live in domain-grouped files:
  - agent_flows.py                    (agent run lifecycle)
  - memory_flows.py                   (compatibility shim to platform memory flows)
  - AINDY.runtime.flow_definitions_engine         (flow run state and registry)
  - system_flows.py                   (automation logs, scheduler, task trigger)
  - AINDY.runtime.flow_definitions_observability (observability endpoints)
  - dashboard_autonomy_flows.py       (dashboard overview, autonomy decisions)
"""
from __future__ import annotations

from AINDY.runtime.flow_engine import FLOW_REGISTRY  # noqa: F401
from AINDY.runtime import (
    flow_definitions_engine,
    flow_definitions_memory,
    flow_definitions_observability,
)

from apps.automation.flows import dashboard_autonomy_flows, system_flows


def register() -> None:
    flow_definitions_memory.register()
    flow_definitions_engine.register()
    system_flows.register()
    flow_definitions_observability.register()
    dashboard_autonomy_flows.register()

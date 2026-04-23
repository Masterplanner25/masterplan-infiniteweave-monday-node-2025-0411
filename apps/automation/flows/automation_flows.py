"""
automation_flows.py - thin delegator.

Node implementations live in domain-grouped files:
  - agent_flows.py                    (agent run lifecycle)
  - AINDY.runtime.flow_definitions_memory         (memory CRUD, recall, search)
  - AINDY.runtime.flow_definitions_engine         (flow run state and registry)
  - automation_system_flows.py        (automation logs, scheduler, task trigger)
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

from apps.automation.flows import (
    automation_system_flows,
    dashboard_autonomy_flows,
)


def register() -> None:
    flow_definitions_memory.register()
    flow_definitions_engine.register()
    automation_system_flows.register()
    flow_definitions_observability.register()
    dashboard_autonomy_flows.register()

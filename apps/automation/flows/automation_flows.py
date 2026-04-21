"""
automation_flows.py - thin delegator.

Node implementations live in domain-grouped files:
  - agent_flows.py                    (agent run lifecycle)
  - memory_flows.py                   (memory CRUD, recall, search)
  - flow_engine_flows.py              (flow run state and registry)
  - automation_system_flows.py        (automation logs, scheduler, task trigger)
  - observability_flows.py            (observability endpoints)
  - watcher_flows.py                  (watcher signals and trigger evaluation)
  - dashboard_autonomy_flows.py       (dashboard overview, autonomy decisions)
"""
from __future__ import annotations

from AINDY.runtime.flow_engine import FLOW_REGISTRY  # noqa: F401

from apps.agent.flows import agent_flows
from apps.automation.flows import (
    automation_system_flows,
    dashboard_autonomy_flows,
    flow_engine_flows,
    memory_flows,
    observability_flows,
    watcher_flows,
)


def register() -> None:
    agent_flows.register()
    memory_flows.register()
    flow_engine_flows.register()
    automation_system_flows.register()
    observability_flows.register()
    watcher_flows.register()
    dashboard_autonomy_flows.register()

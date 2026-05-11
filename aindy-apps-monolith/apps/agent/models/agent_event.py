"""Compatibility shim for runtime-owned agent event persistence."""

from AINDY.db.models.agent_event import AGENT_EVENT_TYPES, AgentEvent

__all__ = ["AGENT_EVENT_TYPES", "AgentEvent"]

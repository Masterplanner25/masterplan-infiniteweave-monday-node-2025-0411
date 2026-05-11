from __future__ import annotations

from typing import Any, Protocol, TypedDict


class PlannerContextPayload(TypedDict, total=False):
    system_prompt: str
    context_block: str


class RunToolDescriptor(TypedDict, total=False):
    name: str
    risk: str
    description: str
    capability: str
    required_capability: str
    category: str
    egress_scope: str


class CapabilityDefinition(TypedDict):
    description: str
    risk_level: str


class CapabilityProviderBundle(TypedDict, total=False):
    definitions: dict[str, CapabilityDefinition]
    tool_capabilities: dict[str, list[str]]
    agent_capabilities: dict[str, list[str]]
    restricted_tools: list[str]


class PlannerContextProvider(Protocol):
    def __call__(self, context: dict[str, Any]) -> PlannerContextPayload: ...


class RunToolProvider(Protocol):
    def __call__(self, context: dict[str, Any]) -> list[RunToolDescriptor]: ...


class CapabilityDefinitionProvider(Protocol):
    def __call__(self) -> CapabilityProviderBundle: ...


class TriggerEvaluator(Protocol):
    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class AgentCompletionHook(Protocol):
    def __call__(self, context: dict[str, Any]) -> Any: ...

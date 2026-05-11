---
title: "Runtime Public API Contract"
last_verified: "2026-05-09"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Runtime Public API Contract

This document is the authoritative import contract between the runtime in
`AINDY/` and the future app repo split. For `aindy-apps-monolith`, only the
modules listed in **Public Runtime API Modules** are stable import targets.
Everything else under `AINDY/` is internal unless it is listed under
**Transitional App Imports To Remove Or Replace**.

## Contract Rules

- Apps may import only the modules listed in **Public Runtime API Modules**.
- Modules listed in **Transitional App Imports To Remove Or Replace** are
  current exceptions, not promoted public API.
- Any `AINDY.*` module not listed in either section is internal runtime
  implementation and must not be imported by apps.
- New app imports from internal runtime modules are regressions.
- New runtime imports from `apps.*` are regressions.

## Public Runtime API Modules

- `AINDY.agents.tool_registry`
- `AINDY.agents.tool_syscalls`
- `AINDY.config`
- `AINDY.db`
- `AINDY.db.database`
- `AINDY.db.model_registry`
- `AINDY.db.models`
- `AINDY.db.mongo_setup`
- `AINDY.kernel.circuit_breaker`
- `AINDY.kernel.errors`
- `AINDY.kernel.syscall_dispatcher`
- `AINDY.kernel.syscall_registry`
- `AINDY.platform_layer.app_runtime`
- `AINDY.platform_layer.async_job_service`
- `AINDY.platform_layer.bootstrap_contract`
- `AINDY.platform_layer.bootstrap_graph`
- `AINDY.platform_layer.deepseek_client`
- `AINDY.platform_layer.deployment_contract`
- `AINDY.platform_layer.domain_health`
- `AINDY.platform_layer.event_service`
- `AINDY.platform_layer.event_trace_service`
- `AINDY.platform_layer.external_call_service`
- `AINDY.platform_layer.memory_runtime`
- `AINDY.platform_layer.metrics`
- `AINDY.platform_layer.openai_client`
- `AINDY.platform_layer.rate_limiter`
- `AINDY.platform_layer.registry`
- `AINDY.platform_layer.response_adapters`
- `AINDY.platform_layer.scheduler_service`
- `AINDY.platform_layer.system_state_service`
- `AINDY.platform_layer.trace_context`
- `AINDY.platform_layer.user_ids`
- `AINDY.platform_layer.watcher_contract`
- `AINDY.runtime.flow_engine`
- `AINDY.runtime.flow_helpers`
- `AINDY.runtime.memory`
- `AINDY.services.auth_service`
- `AINDY.utils`
- `AINDY.utils.uuid_utils`

## Internal Runtime Implementation

All `AINDY.*` modules not listed in **Public Runtime API Modules** are internal
runtime implementation by default.

This includes:

- `AINDY.core.*`
- `AINDY.memory.*` other than the promoted public modules above
- `AINDY.runtime.*` other than `AINDY.runtime.flow_engine`,
  `AINDY.runtime.flow_helpers`, and `AINDY.runtime.memory`
- `AINDY.agents.*` other than `AINDY.agents.tool_registry` and
  `AINDY.agents.tool_syscalls`
- `AINDY.routes.*`
- `AINDY.db.dao.*`
- `AINDY.db.models.*` submodule files; apps should prefer `AINDY.db.models`
  exports when they need runtime-owned ORM types

## Transitional App Imports To Remove Or Replace

- `AINDY.agents.agent_coordinator`
- `AINDY.agents.agent_runtime`
- `AINDY.agents.agent_tools`
- `AINDY.agents.autonomous_controller`
- `AINDY.agents.capability_service`
- `AINDY.agents.stuck_run_service`
- `AINDY.core.execution_dispatcher`
- `AINDY.core.execution_gate`
- `AINDY.core.execution_helper`
- `AINDY.core.execution_signal_helper`
- `AINDY.core.execution_unit_service`
- `AINDY.core.observability_events`
- `AINDY.core.resume_watchdog`
- `AINDY.core.system_event_service`
- `AINDY.core.system_event_types`
- `AINDY.db.dao.memory_node_dao`
- `AINDY.db.models.agent_event`
- `AINDY.db.models.agent_run`
- `AINDY.db.models.background_task_lease`
- `AINDY.db.models.flow_run`
- `AINDY.db.models.job_log`
- `AINDY.db.models.system_event`
- `AINDY.db.models.system_health_log`
- `AINDY.db.models.user`
- `AINDY.db.models.user_identity`
- `AINDY.db.models.waiting_flow_run`
- `AINDY.kernel.event_bus`
- `AINDY.kernel.scheduler_engine`
- `AINDY.memory.bridge`
- `AINDY.memory.memory_helpers`
- `AINDY.memory.memory_persistence`
- `AINDY.memory.memory_scoring_service`
- `AINDY.routes.db_verify_router`
- `AINDY.routes.watcher_router`
- `AINDY.runtime`
- `AINDY.runtime.execution_registry`
- `AINDY.runtime.memory_loop`
- `AINDY.runtime.nodus_execution_service`

## Replacement Direction

- Replace `AINDY.core.*` route and execution helpers with
  `AINDY.platform_layer.app_runtime`, syscall entrypoints, or explicit platform
  contracts.
- Replace `AINDY.db.dao.*` imports with syscall boundaries or public runtime
  service facades.
- Replace `AINDY.db.models.*` submodule imports with `AINDY.db.models` exports
  where direct runtime-owned ORM access is still required.
- Replace `AINDY.agents.autonomous_controller` and other agent-runtime internals
  with explicit plugin contracts in `AINDY.platform_layer.registry`.
- Replace `AINDY.runtime` internal flow-definition imports with public
  registration helpers and runtime-owned boot hooks.
- Replace `AINDY.routes.*` imports with dedicated platform contracts; app code
  must not depend on runtime router implementations.

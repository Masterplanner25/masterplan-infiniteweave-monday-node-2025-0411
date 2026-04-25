# Flow Engine Reference

## Engine A - Custom DAG (Python-defined flows)

**Entry point:** `run_flow()` / `execute_intent()` in `AINDY/runtime/flow_engine/entrypoints.py`, executed by `PersistentFlowRunner.start()` in `AINDY/runtime/flow_engine/runner.py`
**Use for:**
- Flows defined in Python and registered through `register_all_flows()`
- Memory-aware flow nodes from `flow_definitions_memory.py`
- Observability and event-routing flow nodes from `flow_definitions_observability.py`
- Agent, task, automation, and platform orchestration over registered Python nodes

**Node registration:** `NODE_REGISTRY` and `FLOW_REGISTRY` in `AINDY/runtime/flow_engine/registry.py`
**Startup:** `register_all_flows()` plus `flow_definitions_memory.register()`, `flow_definitions_engine.register()`, and `flow_definitions_observability.register()` in `AINDY/main.py`

## Engine B - Nodus VM (script-based execution)

**Entry point:** `run_nodus_script_via_flow()` in `AINDY/runtime/nodus_execution_service.py`, which drives VM execution through `execute_nodus_runtime()` and `NodusRuntimeAdapter`
**Use for:**
- User-authored `.nodus` script execution
- `POST /platform/nodus/*` runtime paths
- Scheduled Nodus jobs in `nodus_schedule_service.py`
- VM-backed `nodus.execute` and `nodus.flow.*` runtime nodes

**Node registration:** `nodus.*` nodes are registered into `NODE_REGISTRY` from `AINDY/runtime/nodus_adapter.py`
**Startup:** Only active when Nodus nodes are registered and `NODUS_SOURCE_PATH` is importable
**Gate:** `AINDY/main.py:_enforce_nodus_gate()`

## Boundary

- Use Engine A for Python flow graphs and normal application orchestration.
- Use Engine B for Nodus scripts and compiled Nodus flows.
- A DAG flow may hand off to a `nodus.*` node, but new code must not use generic `run_flow()` / `execute_intent()` to launch Nodus workflows.
- New flows default to Engine A unless the payload being executed is user-authored Nodus source.

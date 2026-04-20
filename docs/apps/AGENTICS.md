# AGENTICS

This document covers the Agentics app-domain feature: gap analysis, completion
roadmap (Phases A–E), Nodus integration plan, and relationship to other
roadmaps.

For the runtime execution contract — public API, capability enforcement,
per-step retry, recovery/replay, and state machine — see
[docs/runtime/AGENT_RUNTIME.md](../runtime/AGENT_RUNTIME.md).

Date basis: current workspace state.

## 1. System Reality

### What Agentics currently does

Agentics is no longer conceptual. A.I.N.D.Y. already has a functioning
single-agent execution layer built from:

- `services/agent_runtime.py`
- `services/agent_tools.py`
- `services/nodus_adapter.py`
- `services/flow_engine.py`
- `routes/agent_router.py`
- `db/models/agent_run.py`
- `db/models/agent_event.py`
- `services/capability_service.py`

The current lifecycle is:

`goal -> GPT plan -> approval gate -> scoped capability minting -> deterministic execution -> event log -> memory capture -> infinity loop follow-up`

### Production-ready or close to production-ready

- Agent run creation, approval, rejection, replay, recovery, step inspection, and event timeline APIs are implemented in `routes/agent_router.py`.
- The agent planner is live in `services/agent_runtime.py` and uses GPT-generated structured plans over a fixed tool registry.
- The execution path is deterministic in practice because approved plans are executed through `PersistentFlowRunner` in `services/flow_engine.py` via `services/nodus_adapter.py`.
- Per-run scoped capability enforcement exists in `services/capability_service.py` and is checked both before flow execution and before tool execution.
- Agent lifecycle audit persistence exists through `AgentRun`, `AgentStep`, `AgentEvent`, and `SystemEvent`.
- Recovery and replay paths exist through `services/stuck_run_service.py` and `services/agent_runtime.py`.
- The frontend has both an operator console and a dedicated approval inbox:
  - `client/src/components/AgentConsole.jsx`
  - `client/src/components/AgentApprovalInbox.jsx`

### Partially working or transitional

- The execution backbone is A.I.N.D.Y.'s internal flow engine, not the real Nodus DSL/VM path. `services/nodus_adapter.py` is an adapter over `PersistentFlowRunner`, not an adapter over the installed Nodus compiler/VM.
- The Infinity loop is integrated as post-execution orchestration in `services/infinity_orchestrator.py` and `services/infinity_loop.py`, but it is still heuristic and trigger-based rather than autonomous planning/execution.
- Flow execution exists for ARM, task completion, leadgen, genesis message, genesis conversation, memory execution, and watcher ingest, but strategy learning is mostly structural. `select_strategy()` and `update_strategy_score()` exist, yet there is no broad learned strategy corpus driving the system.
- Async execution exists in `services/async_job_service.py`, but it is an in-process thread-pool queue, not a durable distributed worker system.
- The installed Nodus runtime is used only for restricted ad hoc execution through `services/nodus_execution_service.py` and `POST /memory/nodus/execute`, not as the primary execution path for agents or flows.

### Not implemented

- Agent plans are not compiled to `.nd` source, bytecode, or VM programs anywhere in this repository.
- There are no checked-in `.nd` workflow assets in the repo.
- The agent runtime does not execute through the installed Nodus compiler/VM stack.
- Nodus execution traces are not the canonical source of `FlowRun`, `AgentEvent`, or `SystemEvent`.
- Multi-agent delegation and coordination are not implemented.
- Autonomous closed-loop agent execution is not implemented beyond post-run suggestion/orchestration.
- RippleTrace is not yet the unified event intelligence layer for Agentics.

## 2. Architecture (Corrected)

### Current implemented architecture

```text
User / API / UI
  -> Agent Runtime
     (`services/agent_runtime.py`)
  -> Tool Registry + Capability Enforcement
     (`services/agent_tools.py`, `services/capability_service.py`)
  -> Internal Flow Engine
     (`services/flow_engine.py`)
  -> Agent Flow Adapter
     (`services/nodus_adapter.py`)
  -> Domain Services / Tools
     (tasks, memory, ARM, Genesis, LeadGen, watcher)
  -> Event Persistence
     (`AgentEvent`, `SystemEvent`, `FlowRun`, `FlowHistory`)
  -> Memory Capture
     (`services/memory_capture_engine.py`)
  -> Infinity Follow-up
     (`services/infinity_orchestrator.py`, `services/infinity_loop.py`)
```

### Intended corrected architecture

```text
A.I.N.D.Y. = intelligence + planning + policy + orchestration
Nodus      = declarative workflow language + compiler + VM execution layer

Planner / Runtime policy
  -> Nodus workflow selection or generation
  -> Nodus compile / load
  -> Nodus VM execution
  -> execution events + checkpoints
  -> RippleTrace / SystemEvent ledger
  -> Memory Bridge writes + recall feedback
  -> Infinity loop / higher-order orchestration
```

### Component definitions

- Agent Runtime
  - Current role: plan generation, approval, capability minting, run lifecycle management.
  - Primary files: `services/agent_runtime.py`, `routes/agent_router.py`.

- Nodus Execution Layer
  - Intended role: declarative workflow language, compiler, bytecode/VM execution, deterministic traces.
  - Current reality: only partially present through the installed `nodus` package and `services/nodus_execution_service.py`.
  - Not yet the default execution substrate for Agentics.

- Flow Engine
  - Current role: A.I.N.D.Y.'s actual execution backbone.
  - Primary files: `services/flow_engine.py`, `services/flow_definitions.py`, `routes/flow_router.py`.
  - Supports DB-backed state, WAIT/RESUME, flow history, and completion capture.

- Infinity Loop
  - Current role: post-execution score recalculation and next-action suggestion.
  - Primary files: `services/infinity_orchestrator.py`, `services/infinity_loop.py`.
  - Not yet an autonomous agent controller.

- Memory Bridge
  - Current role: recall, capture, federated memory, feedback weighting, and Nodus memory helpers.
  - Primary files: `services/memory_capture_engine.py`, `bridge/nodus_memory_bridge.py`, `routes/memory_router.py`.

- RippleTrace / SystemEvent layer
  - Current role: partially split.
  - Durable execution/event ledger exists in `db/models/system_event.py` and `services/system_event_service.py`.
  - RippleTrace as a higher-order pattern/graph/insight layer remains incomplete.

## 3. Gap Analysis

### Missing capabilities

- Real Nodus-backed agent execution path.
- `.nd` workflow authoring, storage, loading, and versioning inside A.I.N.D.Y.
- Compile-to-bytecode or VM-backed execution for agent plans.
- Unified Nodus trace -> `FlowRun` / `AgentEvent` / `SystemEvent` mapping.
- Agent-to-agent delegation and shared execution contracts.
- Autonomous trigger -> plan -> execute loops without manual initiation.
- Rich egress policy beyond capability checks and per-tool metadata.

### Broken or partial flows

- The naming around "Nodus" is architecturally misleading today:
  - `services/nodus_adapter.py` does not use the installed Nodus VM.
  - the real installed Nodus runtime is only used by `services/nodus_execution_service.py`
- The current agent plan format is JSON from GPT, not a declarative Nodus workflow.
- Memory-side Nodus execution is isolated from the flow engine and agent runtime.
- `select_strategy()` and `update_strategy_score()` exist, but the broader adaptive strategy loop is not yet driving runtime behavior across Agentics.
- Async execution is in-process only, so execution durability and worker isolation are limited.

### Inconsistencies

- The repo has two execution concepts:
  - internal flow execution via `PersistentFlowRunner`
  - embedded Nodus runtime execution via `NodusRuntime`
- Agentics documentation that treats Nodus integration as complete is inaccurate.
- Agentics documentation that says the system is not implemented is also inaccurate.
- RippleTrace is not yet the canonical intelligence layer over execution events.

### Architectural drift

- The internal flow engine has become the de facto execution layer that the long-term architecture intended Nodus to own.
- The term "Nodus" is currently used for both:
  - a future primary execution substrate
  - an existing restricted embedded runtime endpoint
- Without consolidation, A.I.N.D.Y. risks carrying two parallel workflow systems indefinitely.

## 4. Agentics Completion Plan

### Phase A - Execution Integrity

Objective:
- Stabilize the current internal agent/runtime path as the transitional production base.

Required components:
- agent runtime lifecycle hardening
- flow/agent/event consistency
- stronger execution ownership and observability

Exact files/modules affected:
- `services/agent_runtime.py`
- `services/nodus_adapter.py`
- `services/flow_engine.py`
- `services/async_job_service.py`
- `services/stuck_run_service.py`
- `routes/agent_router.py`
- `routes/flow_router.py`
- `client/src/components/AgentConsole.jsx`
- `client/src/components/AgentApprovalInbox.jsx`

Success criteria:
- every agent run has one authoritative execution record path
- queued, running, failed, replayed, and recovered states are fully inspectable
- async execution can be resumed or audited without relying on process memory
- no ambiguity remains between agent run state and linked `FlowRun`

### Phase B - Nodus Integration Completion

Objective:
- Make real Nodus the primary execution substrate instead of the internal flow engine naming shim.

Required components:
- Nodus workflow source management
- compile/load pipeline for `.nd` assets or generated workflows
- VM execution adapter into A.I.N.D.Y.'s DB/event model
- checkpoint and trace mapping

Exact files/modules affected:
- `services/nodus_execution_service.py`
- `services/nodus_adapter.py`
- `services/flow_engine.py`
- `services/system_event_service.py`
- `services/agent_event_service.py`
- `bridge/nodus_memory_bridge.py`
- `routes/memory_router.py`
- `routes/agent_router.py`
- new Nodus workflow asset location in-repo

Success criteria:
- agent execution can run through the installed Nodus compiler/VM path
- `.nd` workflows exist in-repo and are versioned
- Nodus execution emits durable `SystemEvent` and `AgentEvent` records
- `FlowRun` either becomes a Nodus-backed run record or is cleanly superseded

### Phase C - Autonomous Agent Loop

Objective:
- Promote the current post-run Infinity follow-up into a controlled autonomous operating loop.

Required components:
- trigger ingestion
- planner re-entry rules
- policy-based autonomous execution windows
- bounded loop scheduling

Exact files/modules affected:
- `services/infinity_orchestrator.py`
- `services/infinity_loop.py`
- `services/agent_runtime.py`
- `services/system_event_service.py`
- `routes/observability_router.py`
- scheduler integration under `services/`

Success criteria:
- approved triggers can generate bounded autonomous runs
- loop decisions are persisted and replayable
- no infinite execution chains occur without explicit policy
- next-action generation can become next-run generation under controlled conditions

### Phase D - Multi-Agent Coordination

Objective:
- Extend Agentics from single-agent execution to coordinated agent systems.

Required components:
- agent registry integration with runtime
- delegation contracts
- shared/private memory boundaries
- inter-agent event and approval model

Exact files/modules affected:
- `db/models/agent.py`
- `routes/memory_router.py`
- `bridge/nodus_memory_bridge.py`
- `services/agent_runtime.py`
- `services/capability_service.py`
- `services/flow_engine.py`
- new coordination/orchestration service layer

Success criteria:
- one agent can delegate a scoped task to another
- memory sharing rules are explicit and enforced
- capability tokens can be constrained per delegated sub-run
- operator surfaces show parent/child agent relationships

### Phase E - Production Hardening

Objective:
- Harden the completed Agentics layer for long-running, multi-instance operation.

Required components:
- durable worker model
- execution queue isolation
- standardized policy enforcement
- stronger event and trace retention

Exact files/modules affected:
- `services/async_job_service.py`
- `services/system_event_service.py`
- `routes/observability_router.py`
- deployment/runtime configuration
- testing under `tests/`

Success criteria:
- execution survives process restarts and multi-instance deployment
- operator audit views cover agent, flow, and Nodus execution uniformly
- failure handling is deterministic and observable
- automated tests cover agent, flow, and Nodus integration paths end to end

## 5. Integration With Nodus

### Current level of integration

The installed Nodus package is real and available in the venv. It exposes a
compiler/runtime stack and an embedded execution API through
`nodus.runtime.embedding.NodusRuntime`.

Current A.I.N.D.Y. integration points are:

- `services/nodus_execution_service.py`
  - executes source strings through `NodusRuntime.run_source()`
- `services/nodus_security.py`
  - restricts imports, file access, network access, and operation usage
- `bridge/nodus_memory_bridge.py`
  - exposes memory operations such as recall/remember/suggest/record_outcome
- `routes/memory_router.py`
  - exposes `POST /memory/nodus/execute`

### Missing integration points

- Agent runtime does not generate or execute Nodus workflows.
- `services/nodus_adapter.py` does not call the Nodus compiler or VM.
- No repository-managed `.nd` modules or packages exist.
- No bytecode artifacts or compiled workflow cache are stored by A.I.N.D.Y.
- Nodus runtime events are not mapped into `AgentEvent` or `FlowHistory`.
- Nodus is not registered as the execution substrate for flow definitions in `services/flow_definitions.py`.

### Required work to make Nodus the primary execution path

- Define a canonical mapping from agent plan -> Nodus workflow.
- Decide whether plans become:
  - generated `.nd` source
  - templated `.nd` workflows with parameter injection
  - or precompiled Nodus workflow packages
- Replace or wrap `PersistentFlowRunner` with a real Nodus-backed execution adapter.
- Persist Nodus execution traces into A.I.N.D.Y.'s observability model.
- Route memory operations through `NodusMemoryBridge` without isolating them to the memory endpoint only.
- Standardize approval, capability, and egress policy at the Nodus execution boundary.

Verdict:
- Nodus is present.
- Nodus is not yet the primary Agentics execution layer.
- The current system is best described as an internal flow-engine-based Agentics layer with limited embedded Nodus support.

## 6. Relationship to Other Roadmaps

### `TECH_DEBT.md`

Agentics-specific debt now centers on:

- the split between the internal flow engine and real Nodus execution
- single-agent limitations
- incomplete autonomous loop behavior
- in-process async execution durability
- incomplete normalization of execution telemetry across domains

### `EVOLUTION_PLAN.md`

The evolution plan should treat:

- current `PersistentFlowRunner` execution as transitional infrastructure
- Nodus as the target core execution substrate
- Agentics completion as a dedicated evolution phase rather than an assumed completed layer

## Summary

Agentics is implemented enough to be operational today, but it is not complete
and it is not yet the intended A.I.N.D.Y. + Nodus architecture.

Current truth:

- A.I.N.D.Y. has a real agent runtime.
- A.I.N.D.Y. has a real internal deterministic flow engine.
- A.I.N.D.Y. has limited embedded Nodus execution for memory-side tasks.
- A.I.N.D.Y. does not yet run Agentics primarily through real Nodus workflows and VM execution.

That is the baseline this roadmap should be built from.

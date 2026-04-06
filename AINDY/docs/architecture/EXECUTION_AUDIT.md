# Execution Audit

## Status Note

This document is a structural gap audit, not a claim that nothing has changed since it was written.

Several issues called out here have been improved in the current workspace:

- canonical response shape has been standardized on active execution endpoints
- `trace_id` now propagates from request start through execution, loops, agent runs, memory writes, logs, and events
- `SystemEvent` is now the canonical durable activity ledger
- outbound external interactions now emit required `SystemEvent` lifecycle records
- silent `except ...: pass` blocks were removed from active production code
- auth, analytics, ARM, main-calculation, and memory routes now enter a shared route-layer execution pipeline
- a static execution-contract linter now exists at `tools/execution_contract_linter.py`

The remaining FAIL verdicts are about missing system-wide execution-envelope normalization, not absence of observability or eventing.

The linter makes the normalization gap explicit at compile-time:

- route entry must go through `execute_with_pipeline(...)` or `execute_with_pipeline_sync(...)`
- direct memory capture outside `core/execution_pipeline.py` is flagged
- direct event emission outside `core/execution_pipeline.py` is flagged
- service-level execution entry is flagged

At the time of this note, the repo still contains real violations under that rule set, so the linter should be read as an enforcement mechanism plus migration backlog, not as proof that the audit verdicts are fully resolved.

## Scope

This audit checks each execution domain against the canonical execution contract defined in `docs/architecture/EXECUTION_CONTRACT.md`.

Required contract:

`Input -> Execution -> Persist -> Orchestrator -> Observability`

Audit criteria:

- input is typed and traceable
- execution is routed through a structured runtime
- result is durably persisted as part of execution
- orchestrator is mandatory, not best-effort
- observability is part of the execution lifecycle, not an optional mirror
- no silent side effects
- no side-effect-only completion logic

## Verdict Summary

| Domain | Verdict | Reason |
|---|---|---|
| Agent | FAIL | Closest to canonical, but still lacks a system-wide execution envelope |
| Task | FAIL | Direct service mutation path with side effects bolted on after commit |
| Memory | FAIL | Split execution path and separate Nodus executor surface |
| Genesis | FAIL | Direct route/service execution outside a shared execution-record model |
| Watcher | FAIL | Batch ingest persists raw domain rows, then runs follow-up logic non-atomically and optionally |
| ARM | FAIL | Direct analyzer execution with domain persistence, but no shared execution-record model |

## Domain Audit

### Agent

**Verdict:** FAIL

**What follows the contract**

- Structured input exists at the router boundary in `routes/agent_router.py:70-96`.
- Execution is routed through `agents.agent_runtime.create_run()` and `agents.agent_runtime.execute_run()` in `services/agent_runtime.py:254-333` and `services/agent_runtime.py:342-430`.
- Persistence exists through `AgentRun`, `AgentStep`, `AgentEvent`, and `FlowRun`.
- Observability exists via lifecycle events and flow history.
- Flow-backed execution exists via `PersistentFlowRunner` in `services/flow_engine.py:195-415`.

**Where it bypasses the contract**

- Auto-execution can still be initiated from the route after creation, but the synchronous execution path now enters the shared route execution wrapper and the canonical runtime entrypoint rather than a fully separate adapter-owned path.
- The canonical contract still requires one execution envelope for the whole system. Agent now exposes shared `execution_record` metadata, but `AgentRun` plus `FlowRun` still do not read as one fully unified orchestration surface.
- Agent execution now enters a shared execution-record model before runtime work begins, but orchestration ownership is still split above that layer.
- Orchestration ownership is still split across the runtime service and the flow shell, not the runtime service and adapter layers.

**Unstructured side effects**

- KPI prompt enrichment is still non-fatal: `services/agent_runtime.py`.
- Completion-time orchestration ownership is still split between runtime layers.

**Exact violations**

- `routes/agent_router.py`
  Route still chooses between immediate and queued execution paths instead of always entering one identical orchestration surface.
- `agents/agent_runtime.py`
  Agent completion still relies on agent-specific post-processing rather than a single shared execution-orchestrator abstraction.
- `runtime/flow_engine.py` and `runtime/nodus_execution_service.py`
  Flow-shell orchestration and runtime orchestration are narrower than before, but still split responsibility above the canonical runtime entrypoint.

**Recommended fixes**

1. Replace route-level `create -> maybe execute` with one `ExecutionRunner.run()` entrypoint for agent work.
2. Move all post-completion orchestration into one shared orchestrator stage.
3. Remove the remaining split ownership between `agent_runtime`, `flow_engine`, and `nodus_execution_service`; keep exactly one owner above the runtime layer.
4. Introduce a system-wide execution envelope and map `AgentRun` to domain state inside it.

### Task

**Verdict:** FAIL

**What follows the contract**

- Input is explicit at `routes/task_router.py:14-56`.
- Core domain mutation is persisted in `services/task_services.py`.

**Where it bypasses the contract**

- Task routes now enter a shared route wrapper, but the task domain still calls task services directly after the route boundary rather than a single persisted execution-record runtime.
- `create_task`, `start_task`, `pause_task`, and `complete_task` all mutate domain state directly and return user-facing values without a canonical execution envelope: `services/task_services.py:140-205` and `services/task_services.py:209-340`.
- `complete_task` commits the primary write before memory, feedback, ETA, social sync, or orchestration happen: `services/task_services.py:222-224`.

**Unstructured side effects**

- Memory capture and feedback now log and emit observability on failure rather than silently disappearing, but they are still post-commit side effects.
- Social sync is external side-effect after commit: `services/task_services.py:290-310`.
- ETA recalculation is best-effort after commit: `services/task_services.py:312-325`.
- Infinity orchestration is best-effort after commit: `services/task_services.py:327-338`.

**Exact violations**

- `routes/task_router.py:14-56`
  Route-to-service direct execution path, no shared runtime.
- `services/task_services.py:222-224`
  Task is marked completed and committed before orchestration starts.
- `services/task_services.py:226-243`
  Memory capture can silently fail.
- `services/task_services.py:245-274`
  Feedback is unstructured and optional.
- `services/task_services.py:290-310`
  External Mongo side effect happens outside execution structure.
- `services/task_services.py:312-338`
  ETA and Infinity orchestration are best-effort follow-ons.

**Recommended fixes**

1. Wrap all task actions in a canonical `task.*` execution runner.
2. Persist a canonical execution record before task mutation.
3. Move memory, social sync, ETA, and score updates into ordered orchestration steps.
4. Return a structured execution result instead of raw strings from task services.

### Memory

**Verdict:** FAIL

**What follows the contract**

- `ExecutionLoop` does have a recognizable pipeline: recall, execute, persist memory output, feedback, metrics.
- Trace persistence exists through `MemoryTraceDAO`.
- Memory routes now enter a shared route-layer execution pipeline before domain work begins.

**Where it bypasses the contract**

- `/memory/execute` has been moved into the canonical flow path, and `/memory/nodus/execute` now reuses the same canonical Nodus runtime/result helpers, but the route still preserves a separate top-level outer envelope.
- `/memory/execute/complete` is deprecated compatibility surface and not part of the canonical path.
- `/memory/nodus/execute` is no longer a fully separate execution engine, but it still has route-specific lifecycle and envelope handling above the canonical runtime helpers: `routes/memory_router.py`.

**Unstructured side effects**

- The prior silent side-effect blocks were removed; failures are now logged and surfaced instead of swallowed.

**Exact violations**

- `routes/memory_router.py`
  Nodus path still keeps route-specific outer handling even though the inner runtime path is now canonical.
- `routes/memory_router.py:1021-1088`
  Deprecated completion endpoint still exposes the old split-path model.

**Recommended fixes**

1. Remove the deprecated `/memory/execute/complete` compatibility endpoint once clients are migrated.
2. Move Nodus execution behind the same shared execution contract or isolate it as a formally separate executor with the same contract guarantees.
3. Keep Nodus restrictions aligned with the agent capability model so read-only and write-capable operations do not drift.

### Genesis

**Verdict:** FAIL

**What follows the contract**

- Inputs are explicit for session creation, message, synthesize, lock, and activate.
- Domain persistence exists for `GenesisSessionDB` and `MasterPlan`.

**Where it bypasses the contract**

- Genesis still performs domain-specific work outside a shared execution-record model.
- `lock_masterplan` and `activate_masterplan` perform domain writes first and then emit memory side effects separately: `routes/genesis_router.py:308-345` and `routes/genesis_router.py:374-401`.

**Unstructured side effects**

- Outbound model calls are now durably evented, but Genesis actions still do not enter a system-wide execution envelope.

**Exact violations**

- `routes/genesis_router.py:89-115`
  Direct route-level execution and persistence.
- `routes/genesis_router.py:117-157`
  Genesis still executes as a domain-specific path rather than through a shared execution-record model.
- `routes/genesis_router.py:321-345`
  Lock event memory capture is optional.
- `routes/genesis_router.py:374-401`
  Activation does direct mutation then optional memory capture.

**Recommended fixes**

1. Move `message`, `synthesize`, `lock`, and `activate` into domain executors behind the shared runtime.
2. Make flow execution primary, not a secondary observability mirror.
3. Make orchestration mandatory after session or masterplan state changes.
4. Persist a canonical execution result for every Genesis action, including `next_action`.

### Watcher

**Verdict:** FAIL

**What follows the contract**

- Input validation is present for batch ingest in `routes/watcher_router.py:143-173`.
- Raw domain persistence exists for `WatcherSignal`: `routes/watcher_router.py:175-194`.

**Where it bypasses the contract**

- The watcher path only persists raw signals, not a canonical execution lifecycle.
- Follow-up logic is triggered after commit through `_trigger_eta_update()`: `routes/watcher_router.py:115-136` and `routes/watcher_router.py:194-198`.
- Orchestration is conditional on the presence of a `user_id`, which means the same ingest path can bypass the orchestrator entirely: `routes/watcher_router.py:125-136`.

**Unstructured side effects**

- Outbound watcher delivery is now externally instrumented, but ingest follow-on work still depends on route-level post-commit logic.

**Exact violations**

- `routes/watcher_router.py:115-136`
  Post-ingest orchestration is optional and failure-tolerant.
- `routes/watcher_router.py:176-194`
  Raw signal rows are the only persisted record of execution.
- `routes/watcher_router.py:197-198`
  Follow-up work starts only after the batch commit completes.

**Recommended fixes**

1. Treat watcher ingest as a canonical execution type such as `watcher.ingest`.
2. Persist one execution envelope per batch ingest, not just per raw signal.
3. Move ETA and Infinity work into the orchestrator stage.
4. Persist an ingest summary and next action, even when there is no user-bound recalculation.

### ARM

**Verdict:** FAIL

**What follows the contract**

- Router input is explicit in `routes/arm_router.py:77-120`.
- ARM routes now enter a shared route-layer execution pipeline before domain work begins.
- Domain persistence exists in `analysis_results` and `code_generations`.
- Failure logging and outbound model-call eventing exist for ARM analysis/generation.

**Where it bypasses the contract**

- The analyzer still executes directly after the route boundary; the route is now wrapped, but there is still no shared persisted execution-record runtime for ARM.
- `run_analysis()` and `generate_code()` persist domain records and return immediately, with orchestration and memory treated as follow-on work: `modules/deepseek/deepseek_code_analyzer.py:286-341` and `modules/deepseek/deepseek_code_analyzer.py:457-501`.
- `generate_code()` has no Infinity orchestration stage at all.

**Unstructured side effects**

- Infinity orchestration after analysis is still follow-on work rather than part of a shared execution envelope.
- Recalled-memory feedback is optional: `modules/deepseek/deepseek_code_analyzer.py:302-321`.
- Memory capture is optional for both analysis and generation: `modules/deepseek/deepseek_code_analyzer.py:323-341` and `modules/deepseek/deepseek_code_analyzer.py:476-493`.
- Identity observation failures are logged, but the work still sits outside a shared orchestrator abstraction.

**Exact violations**

- `routes/arm_router.py:94-102`
  Analyze path bypasses shared execution runtime.
- `routes/arm_router.py:117-120`
  Generate path bypasses shared execution runtime.
- `modules/deepseek/deepseek_code_analyzer.py:286-341`
  Analysis persists first, then runs optional score and memory side effects.
- `modules/deepseek/deepseek_code_analyzer.py:457-501`
  Code generation persists first and only does optional memory capture; no mandatory orchestrator stage.
- `modules/deepseek/deepseek_code_analyzer.py:205-219`
  Identity side effects are silently ignored.

**Recommended fixes**

1. Put `arm.analyze` and `arm.generate` behind the shared execution runtime.
2. Persist a canonical execution record before analyzer work starts.
3. Make orchestration mandatory for both analysis and generation.
4. Move memory and identity side effects into the orchestrator stage.

## Cross-Domain Findings

### Common contract violations

- direct route-to-service execution
- commit-first, orchestrate-later design
- event coverage is much stronger than execution-envelope normalization
- multiple runtimes with different semantics
- observability is now materially better, but execution normalization is still incomplete

### Most common failure mode

The dominant pattern in the codebase is:

`domain write -> commit -> best-effort memory/metrics/score/logging`

That is not the canonical contract.

### Main structural problem

The system does not yet have one shared execution envelope that all domains must enter before domain work begins.

Agent is the closest subsystem to the target shape because it already has:

- a durable run record
- step-level persistence
- lifecycle events
- flow-backed execution

But even agent still fails the canonical contract because the cross-system execution model is not unified.

## Recommended Remediation Order

1. Introduce a shared `ExecutionRecord` model and `ExecutionRunner`.
2. Make every execution route create an execution record before domain mutation.
3. Centralize post-execution work behind one `ExecutionOrchestrator`.
4. Remove split or mirrored runtimes:
   - route-level auto-execute
   - deprecated `/memory/execute/complete` compatibility path
   - genesis observability-only flow mirroring
5. Keep silent-failure paths out of execution-critical code and require explicit logging/observability on degraded side effects.
6. Standardize all responses on canonical execution output:
   - status
   - persisted domain result
   - orchestration result
   - next action
   - observability references

## Bottom Line

Every audited domain still fails the canonical execution contract in the strict system-design sense.

The reason is not lack of persistence or lack of features. The reason is structural inconsistency:

- execution is not forced through one runtime
- orchestration is often optional
- side effects are tolerated as non-fatal
- eventing and traceability are stronger than the remaining execution-structure gaps

Until every domain obeys:

`Input -> Execution -> Persist -> Orchestrator -> Observability`

the system does not have a single canonical execution model.


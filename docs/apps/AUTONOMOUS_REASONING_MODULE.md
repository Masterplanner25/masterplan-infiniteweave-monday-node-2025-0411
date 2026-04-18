# AUTONOMOUS REASONING MODULE (ARM)

## 1. System Reality

### What this document means now

The existing codebase uses the name "ARM" for a code analysis and code generation subsystem exposed at `/arm/*` and implemented primarily in:

- `routes/arm_router.py`
- `apps/arm/services/deepseek/deepseek_code_analyzer.py`
- `services/arm_metrics_service.py`

That subsystem is real, but it is **not** the full autonomous reasoning layer A.I.N.D.Y. would need in order to decide what to do next across the system.

If "Autonomous Reasoning" is defined correctly as:

- evaluating system state
- interpreting memory and metrics
- selecting next actions
- adapting strategy over time

then the current system only implements this **partially**.

### What exists today

#### Implemented

- `services/infinity_orchestrator.py`
  - collects recent memory and KPI state
  - recalculates Infinity score
  - executes the loop decision step
  - emits `loop.started` and `loop.decision` events

- `services/infinity_loop.py`
  - contains the clearest existing system-level decision logic
  - evaluates recent feedback, KPI thresholds, incomplete tasks, and cooldown windows
  - outputs a `decision_type`, `adjustment_payload`, and `next_action`

- `services/agent_runtime.py`
  - generates plans for explicit user goals
  - injects Infinity KPI context into planning
  - triggers the Infinity orchestrator after successful completion

- `services/flow_engine.py`
  - contains lightweight strategy selection and strategy score updates for execution flows
  - compiles intent into executable internal flows

- `runtime/memory/orchestrator.py`
  - performs memory retrieval strategy selection, scoring, and filtering
  - this is meaningful reasoning for memory recall, but not a general decision layer

- `services/system_event_service.py`
  - provides durable event emission so some loop decisions are observable

#### Partially implemented

- Memory-informed decision making
  - the Infinity orchestrator reads recent memory before making a loop decision
  - the agent planner uses KPI context
  - ARM analysis uses memory recall and writes memory back
  - however, there is no dedicated reasoning service that treats memory as a first-class decision input across the platform

- Adaptive strategy selection
  - flow strategies and memory retrieval strategies exist
  - they are local optimization mechanisms, not a unified system-level reasoning engine

- Observability for decisions
  - some decisions are emitted as `SystemEvent`s
  - there is no dedicated reasoning event schema, no consistent explanation model, and no full trace of why decisions were made

#### Not implemented

- a dedicated autonomous reasoning service or module
- a normalized system-state evaluator
- a reusable decision engine that can choose actions for agents, loops, and workflows
- structured strategy selection beyond hard-coded heuristics
- reasoning output as a standard contract consumable by Agent Runtime and Nodus
- reasoning-driven Nodus workflow selection or compilation
- explicit reasoning events across all decision points

## 2. What the Current "ARM" Actually Is

The current `/arm` subsystem is best described as:

- a code analysis and generation engine
- backed by `DeepSeekCodeAnalyzer`
- instrumented with ARM-specific metrics
- connected to memory capture and Infinity score recalculation

It is **not** the platform's general autonomous reasoning layer.

That distinction matters:

- ARM today: reason about source code and return analysis or generated code
- Autonomous Reasoning target: reason about system state and choose what A.I.N.D.Y. should do next

The name has drifted away from the actual architecture.

## 3. Corrected Architecture

### Layer boundaries

#### Autonomous Reasoning Layer

Purpose:

- decide what should happen next
- evaluate current state, memory, metrics, and feedback
- choose next actions, priorities, and strategies

Target components:

- `state_evaluator`
- `decision_engine`
- `strategy_selector`
- `feedback_analyzer`
- `reasoning_event_emitter`

#### Execution Layer

Purpose:

- perform the work chosen by reasoning

Current execution components:

- `services/agent_runtime.py`
- `services/flow_engine.py`
- `services/nodus_adapter.py`
- `services/nodus_execution_service.py`

#### Memory Layer

Purpose:

- provide recall, suggestions, outcomes, and learned signals

Current memory components:

- `runtime/memory/orchestrator.py`
- `services/memory_capture_engine.py`
- `bridge/nodus_memory_bridge.py`

#### Event Layer / RippleTrace

Purpose:

- make decisions and execution visible as durable events

Current event components:

- `services/system_event_service.py`
- `db.models.system_event`
- `db.models.agent_run_event`

### Integration map

#### Autonomous Reasoning -> Agent Runtime

Target:

- reasoning selects or adjusts agent goals, priorities, and execution strategies

Current reality:

- limited
- `agent_runtime.generate_plan()` uses Infinity KPI context
- `agent_runtime.execute_run()` receives a post-execution `next_action` from the Infinity orchestrator
- agents are still mostly goal executors, not reasoning-driven autonomous actors

#### Autonomous Reasoning -> Nodus Execution Layer

Target:

- reasoning emits workflow intents or plans that compile into Nodus execution paths

Current reality:

- effectively absent
- `services/nodus_adapter.py` is an internal flow adapter around `PersistentFlowRunner`, not primary Nodus VM orchestration
- `services/nodus_execution_service.py` executes restricted embedded Nodus source, but this is isolated and not driven by a reasoning engine

#### Autonomous Reasoning -> Infinity Loop

Target:

- Infinity loop becomes one consumer of a reusable reasoning engine

Current reality:

- the Infinity loop is the main place where system-level reasoning currently lives
- its logic is rule-based and tightly coupled to loop execution and task adjustment

#### Autonomous Reasoning -> Memory Bridge

Target:

- memory is a primary input into state evaluation and strategy selection

Current reality:

- partial
- the Infinity orchestrator reads recent memory
- ARM analysis uses memory recall heavily
- memory retrieval itself has strategy selection
- there is no platform-wide reasoning contract that consumes memory uniformly

#### Autonomous Reasoning -> RippleTrace / SystemEvent

Target:

- every significant reasoning step emits observable, queryable decision events

Current reality:

- partial
- loop start and loop decisions are emitted
- many planning and selection decisions remain opaque or embedded in service-local logic

## 4. Relationship to Major Systems

### A. Agent Runtime

Reasoning influences agent execution only indirectly.

What is real:

- planner prompts include KPI context from Infinity scores
- approval and capability checks constrain execution
- completed agent runs trigger the Infinity orchestrator, which may return a `next_action`

What is missing:

- no dedicated reasoning service selecting agent goals
- no persistent strategy model influencing future agent plans
- no standardized reasoning output attached to agent runs before execution starts

### B. Nodus

Nodus is currently an execution concern, not a reasoning consumer.

What is real:

- embedded Nodus execution exists through `services/nodus_execution_service.py`
- memory bridge functions are exposed to Nodus runtime

What is missing:

- no reasoning-to-Nodus plan contract
- no autonomous selection of `.nd` workflows
- no Nodus-first execution path for reasoning outputs

### C. Infinity Loop

The Infinity loop is the current de facto reasoning layer.

What is real:

- threshold-based decision rules
- feedback-aware branch selection
- task reprioritization and next-action generation
- throttling against repeated decisions

What is missing:

- modular reasoning components
- explainable state evaluation beyond simple rules
- reusable output for other orchestration paths

### D. Memory Bridge

Memory affects behavior, but not yet as a unified decision substrate.

What is real:

- recent memory is fed into the Infinity orchestrator
- memory retrieval uses strategy and scoring
- ARM recalls memory and records outcomes

What is missing:

- structured memory summaries for system-level decision making
- explicit memory-derived features for planning and action selection
- closed-loop learning from decision outcomes at the reasoning layer

### E. RippleTrace / SystemEvent

Decision observability exists, but only in fragments.

What is real:

- loop decisions are emitted as events
- execution events and failures are durable

What is missing:

- a reasoning event vocabulary
- decision explanation fields normalized across services
- traceability from observed state -> chosen strategy -> chosen action -> outcome

## 5. Gap Analysis

### Missing reasoning components

- dedicated autonomous reasoning service
- normalized state evaluator
- strategy selection service for system actions
- feedback analyzer tied to future decision policy
- reasoning output schema
- reasoning event schema

### Duplicated or scattered logic

- next-action logic in `services/infinity_loop.py`
- KPI-driven planning influence in `services/agent_runtime.py`
- strategy selection in `services/flow_engine.py`
- memory strategy selection in `runtime/memory/orchestrator.py`
- ARM-specific suggestion logic in `services/arm_metrics_service.py`

These all represent local reasoning fragments, but they are not composed into a single reasoning layer.

### Implicit reasoning that is not formalized

- threshold evaluation of KPI health
- task reprioritization based on execution/focus conditions
- memory retrieval strategy choice
- strategy score updates in the flow engine
- ARM configuration suggestions from performance data

### Architectural inconsistencies

- "ARM" refers to a code-analysis subsystem, not the real platform reasoning layer
- the Infinity loop contains decision logic that should live in a reusable reasoning service
- Nodus exists as execution infrastructure but is not integrated with reasoning outputs
- reasoning decisions are only partially visible in RippleTrace/SystemEvent

## 6. The True Autonomous Reasoning Layer

The correct long-term design is a dedicated layer between state collection and execution.

### Inputs

- recent memory and memory summaries
- Infinity KPI snapshots
- task and workflow state
- recent `SystemEvent` and `AgentEvent` history
- execution outcomes and feedback
- capability and approval constraints

### Core components

#### State Evaluator

Responsibilities:

- aggregate KPIs, memory summaries, recent outcomes, pending work, and event context
- produce a normalized system-state snapshot

Primary files to introduce or refactor toward:

- `services/autonomous_reasoning_service.py`
- `services/reasoning/state_evaluator.py`

#### Decision Engine

Responsibilities:

- map state snapshots to a recommended next action
- support both deterministic rules and later learned policies

Primary files:

- `services/reasoning/decision_engine.py`

#### Strategy Selector

Responsibilities:

- choose execution strategy, workflow type, or escalation path
- unify concepts currently split across flow strategies and memory retrieval strategies

Primary files:

- `services/reasoning/strategy_selector.py`

#### Feedback Analyzer

Responsibilities:

- learn from outcomes, rejections, failures, task completion quality, and user feedback
- update decision policy inputs without embedding that logic separately in each service

Primary files:

- `services/reasoning/feedback_analyzer.py`

#### Reasoning Event Emitter

Responsibilities:

- emit observable reasoning records with:
  - input summary
  - chosen strategy
  - chosen action
  - explanation
  - confidence

Primary files:

- `services/reasoning/reasoning_events.py`
- `services/system_event_service.py`

### Outputs

- `next_action`
- `decision_type`
- `priority_changes`
- `strategy_selection`
- `execution_intent`
- `explanation`
- `confidence`

## 7. Completion Plan

### Phase 1. Extract reasoning from the Infinity loop

Objective:

- separate decision logic from loop orchestration and persistence

Files to modify:

- `services/infinity_loop.py`
- `services/infinity_orchestrator.py`
- `services/infinity_service.py`

Files to create:

- `services/reasoning/state_evaluator.py`
- `services/reasoning/decision_engine.py`
- `services/reasoning/types.py`

Expected behavior:

- the Infinity orchestrator gathers context and calls a reusable reasoning engine
- `infinity_loop.py` becomes primarily loop execution, cooldown, and persistence orchestration

Success criteria:

- loop decisions are generated by shared reasoning code rather than service-local branching
- output is a normalized reasoning result object

### Phase 2. Create a dedicated reasoning service

Objective:

- establish Autonomous Reasoning as a first-class system layer

Files to create:

- `services/autonomous_reasoning_service.py`
- `services/reasoning/strategy_selector.py`
- `services/reasoning/feedback_analyzer.py`

Files to modify:

- `runtime/memory/orchestrator.py`
- `services/memory_capture_engine.py`

Expected behavior:

- reasoning service can evaluate current state without being tied only to the Infinity loop
- memory-derived signals become standardized reasoning inputs

Success criteria:

- one service can answer "what should happen next?" for multiple callers
- memory, score, and event summaries are consumed through a common interface

### Phase 3. Integrate with Agent Runtime

Objective:

- make reasoning influence agent execution before and after runs

Files to modify:

- `services/agent_runtime.py`
- `services/capability_service.py`
- `services/nodus_adapter.py`
- `db/models/agent_run.py`
- `db/models/agent_run_event.py`

Expected behavior:

- agent runs include a pre-execution reasoning result
- plan generation and execution strategy selection use reasoning outputs
- post-run feedback updates the reasoning layer

Success criteria:

- agent runs record why they were launched, why a strategy was chosen, and what next action was derived afterward

### Phase 4. Integrate with Nodus workflows

Objective:

- make reasoning outputs drive Nodus-oriented execution rather than only internal flows

Files to modify:

- `services/nodus_adapter.py`
- `services/nodus_execution_service.py`
- `services/flow_engine.py`
- `bridge/nodus_memory_bridge.py`

Potential files to introduce:

- `services/reasoning/nodus_compiler_adapter.py`
- `runtime/nodus/` integration helpers if execution contracts need to be separated from existing services

Expected behavior:

- reasoning can output an execution intent that selects a Nodus workflow or compiles into one
- Nodus becomes a primary execution consumer of reasoning results rather than an isolated utility path

Success criteria:

- at least one autonomous reasoning outcome can execute through a Nodus-first path with durable traceability

### Phase 5. Add reasoning observability

Objective:

- make reasoning decisions inspectable through RippleTrace / SystemEvent

Files to modify:

- `services/system_event_service.py`
- `services/infinity_orchestrator.py`
- `services/agent_runtime.py`
- `services/nodus_adapter.py`
- observability UI and routes that consume `SystemEvent`

Potential DB changes:

- extend `SystemEvent` payload conventions or add a dedicated reasoning event model if current payload shape becomes too loose

Expected behavior:

- reasoning steps emit standard events such as:
  - `reasoning.state_evaluated`
  - `reasoning.strategy_selected`
  - `reasoning.action_selected`
  - `reasoning.feedback_applied`

Success criteria:

- operators can trace state -> decision -> execution -> outcome through events

## 8. Distinction Between Reasoning, Execution, Memory, and Events

### Reasoning

Decides:

- what to do next
- why that action should be chosen
- what strategy should be used

### Execution

Performs:

- workflows
- tool calls
- step completion
- task mutation

### Memory

Supplies:

- context
- prior outcomes
- reusable patterns
- recall candidates and suggestions

### Events / RippleTrace

Records:

- what was evaluated
- what was decided
- what was executed
- what happened afterward

## 9. Alignment with Other Roadmaps

### AGENTICS.md

This document aligns with `docs/apps/AGENTICS.md`:

- Agentics currently has execution infrastructure and a partial decision loop
- the reasoning layer is not complete
- Nodus is not yet the primary execution path for autonomous system behavior

### EVOLUTION_PLAN.md

This document aligns with `docs/apps/EVOLUTION_PLAN.md`:

- the platform can progress toward autonomous operation only after a real reasoning layer exists
- the reasoning layer should become the bridge between system state and execution

### TECH_DEBT.md

This document aligns with `docs/platform/engineering/TECH_DEBT.md`:

- reasoning debt is currently architectural, not cosmetic
- the main debt is fragmentation: decision logic is spread across loop logic, planner prompts, flow strategy code, and memory orchestration

## 10. Final Assessment

Autonomous Reasoning is **partially real**, but not as a formal module.

What is real today:

- a rule-based decision loop in `services/infinity_loop.py`
- KPI-informed orchestration in `services/infinity_orchestrator.py`
- local reasoning fragments in memory retrieval, flow strategy selection, and ARM-specific analytics

What is not real today:

- a dedicated, reusable autonomous reasoning layer
- reasoning-driven Nodus workflow execution
- full observability of decision rationale

The current `/arm` subsystem should be treated as a specialized code reasoning product surface, not as proof that the broader Autonomous Reasoning layer already exists.

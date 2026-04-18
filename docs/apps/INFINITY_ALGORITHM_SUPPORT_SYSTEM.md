# Infinity Algorithm Support System - Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Infinity Algorithm Support System is the **signal, observation, and feedback infrastructure** that enables the Infinity Algorithm to function as a real system.

It is not the algorithm itself.

It is the system that:

* generates inputs (tasks)
* observes behavior (watcher)
* captures feedback (user + system)
* enables iteration over time

Without this layer, the Infinity Algorithm reduces to a **static metrics engine**.

---

## 2. Core System Role

The Support System transforms:

```plaintext
Human Activity -> Structured Signals -> Algorithm Inputs
```

And enables:

```plaintext
Observation -> Feedback -> Adjustment -> Re-execution
```

---

## 3. Core Components

---

### 3.1 Input Layer - Task System

**Source of structured execution data**

#### Implementation

* `db/models/task.py`
* `routes/task_router.py`
* `services/task_services.py`

#### Signals Generated

* Time (`time_spent`)
* Completion (status transitions)
* Complexity (`task_complexity`)
* Skill (`skill_level`)
* AI Utilization (`ai_utilization`)
* Difficulty (`task_difficulty`)
* Priority (present but not connected)

#### Flow

```plaintext
User Action -> Task API -> Task Service -> DB -> Algorithm Input
```

#### Reality

* **Partially implemented**
* Generates valid inputs for TWR and metrics
* Dependency-aware task execution and blocked/unblocked task state are now part of the live signal layer

---

### 3.2 Observation Layer - Watcher (CRITICAL)

**Real-time behavioral observation system**

#### Source

* `The Masterplan SaaS/Watcher.txt`

#### Intended Capabilities

* Focus tracking (start/stop)
* Pomodoro/session tracking
* Distraction detection:

  * manual (user input)
  * automatic (system monitoring)
* Task duration and attention tracking

#### Intended Outputs

* `focus_session`
* `distraction_detected`
* `time_on_task`
* behavioral logs

#### Execution Model

* Time-based loop (polling system state)
* Potential use of system-level monitoring (e.g., active window/process tracking)

#### Reality

* **Implemented in runtime**
* Watcher signals are stored in `watcher_signals`
* `focus_quality` scoring reads `session_ended`, `distraction_detected`, and `focus_achieved`
* Remaining gap: watcher data influences loop decisions through KPI state, but does not yet modify the standalone TWR formula directly

#### Impact

Without this layer:

* The system cannot observe real execution behavior
* The algorithm operates on incomplete data

---

### 3.3 Feedback Layer - User + System

**Mechanism for behavioral adaptation**

---

#### 3.3.1 System Feedback (Implemented)

##### ARM Metrics

* `services/arm_metrics_service.py`
* `routes/arm_router.py`

Metrics:

* Execution Speed
* Decision Efficiency
* AI Productivity Boost
* Lost Potential
* Learning Efficiency

##### Behavior

* Computes performance insights
* Generates suggestions via `ARMConfigSuggestionEngine`

##### Reality

* **Partially implemented**
* Feedback exists but is:

  * advisory
  * not enforced

---

#### 3.3.2 User Feedback

##### Source

* Algorithm Creation Discussion

##### Intended Signals

* Engagement
* Satisfaction
* Behavioral adjustments
* Outcome evaluation

##### Types

* Explicit (user input)
* Implicit (behavior patterns)

##### Reality

* **Implemented (explicit + partial implicit)**
* `POST /scores/feedback` writes `UserFeedback`
* ARM and agent UI surfaces can submit thumbs feedback
* System behavior now emits implicit feedback signals for retries, repeated failures, latency spikes, and abandonment
* Remaining gap: richer satisfaction signals and formula-level policy learning are still missing

---

## 4. Signal Flow (Current vs Intended)

---

### Current System (Reality)

```plaintext
Task / Watcher / ARM / Agent Outcome
-> Score recalculation
-> Loop decision
-> Task reprioritization or suggestion refresh
-> Explicit feedback capture
-> Re-score
```

---

### Intended System (Canonical)

```plaintext
Task -> Watcher -> Signals -> Algorithm -> Score
     -> Feedback -> Adjustment -> Execution -> Repeat
```

---

## 5. Connection to Infinity Algorithm

---

### Inputs Feeding the Algorithm (Implemented)

* Task-derived signals:

  * time_spent
  * task_complexity
  * skill_level
  * ai_utilization
  * task_difficulty

---

### Signals Influencing Scoring (Implemented)

* Engagement
* Impact
* AI efficiency
* ARM task priority (separate system)
* memory-derived failure/success/pattern signals now influence `run_loop()` decision selection

---

### Signals Defined but NOT Fully Used

* Watcher-derived focus/distraction no longer needs a standalone TWR control path because the legacy route now delegates to Infinity; remaining work is deeper weighting and learning inside the live Infinity path
* Task priority is now adjusted by the loop, but not yet used as an input weighting term
* Broader user satisfaction / engagement input is still missing beyond explicit thumbs feedback
* Memory signals affect loop decisions, but do not yet alter KPI formulas or learned thresholding

---

## 6. System Classification

The Support System is:

> A hybrid data pipeline, observability system, and feedback infrastructure.

It currently functions as:

* Data pipeline -> implemented
* Observability -> implemented
* Feedback engine -> partial
* Support-state aggregation -> distributed across services

---

## 7. Evolution Plan

---

### Phase v1 - Input Stabilization

**Goal:** Ensure reliable data foundation

* Validate all task inputs
* Normalize metric generation
* Connect task priority to scoring

---

### Phase v2 - Watcher Implementation (CRITICAL)

**Status:** Implemented

* Watcher runtime, signal receiver, and `watcher_signals` persistence are live
* Focus tracking, distraction detection, session logging, and heartbeat signals are stored

---

### Phase v3 - Signal Integration

**Status:** Implemented partially

* Watcher outputs feed `focus_quality`
* `focus_quality` now drives loop decisions through `run_loop()`
* Remaining work:

  * broader engagement weighting
  * deeper learned weighting rather than heuristic weighting

---

### Phase v4 - Feedback Enforcement

**Status:** Implemented

* Loop decisions now produce:

  * automatic task reprioritization OR
  * persisted suggestion refresh
* Feedback is connected to execution behavior through `LoopAdjustment` + `UserFeedback`

---

### Phase v5 - User Feedback Integration

**Status:** Implemented partially

* Explicit thumbs feedback exists for ARM and agent outcomes
* Implicit feedback signals now exist for retries, repeated failures, latency spikes, and abandonment
* Remaining work:

  * richer satisfaction signals
  * weighting feedback directly into score formulas

---

### Phase v6 - Full Closed Loop

**Goal:** True self-improving system

```plaintext
observe -> score -> adjust -> execute -> observe
```

* Enforce recurrence
* Remove manual-only feedback dependency

---

## 8. Technical Debt

---

### Structural

* Feedback persistence exists but weighting into score formulas is still limited
* Loop decisions are rule-based rather than learned
* Support state is distributed across task, watcher, memory, event, and observability services rather than centralized

---

### Functional

* Feedback is captured and evaluated, but does not yet alter KPI weights directly
* Request metrics and system health are observable, but not yet used directly by Infinity decisions
* The new memory-weighted loop path is heuristic and still lacks end-to-end behavioral test coverage

---

### Conceptual

* The system is now closed-loop at the execution layer
* Remaining conceptual gap is optimization depth, not loop existence

---

## 9. Phase Mapping

| Phase | Component | Status | Required Action |
| ----- | --------- | ------ | --------------- |
| v1 | Task Inputs | Implemented | Deepen weighting |
| v2 | Watcher | Implemented | Extend coverage |
| v3 | Signal Integration | Partial | Deepen learning |
| v4 | Feedback Enforcement | Implemented | Refine policy |
| v5 | User Feedback | Partial | Expand weighting |
| v6 | Closed Loop | Implemented (MVP) | Optimize |

---

## 10. Next Steps

### Step 1 - Centralize support-system state
**Files:** new support-state service, `services/infinity_orchestrator.py`, `services/identity_boot_service.py`  
**Outcome:** Infinity receives one consistent state snapshot instead of assembling support inputs ad hoc.

### Step 2 - Feed more support metrics into loop decisions
**Files:** `services/infinity_loop.py`, `services/infinity_service.py`  
**Outcome:** watcher, feedback, and execution support signals influence decisions more directly.

### Step 3 - Connect observability aggregates to support inputs
**Files:** `routes/observability_router.py`, supporting services/models as needed  
**Outcome:** request metrics and health data become usable support inputs rather than dashboard-only outputs.

### Step 4 - Aggregate agent and async execution behavior into support metrics
**Files:** `services/agent_event_service.py`, `services/async_job_service.py`, `services/infinity_service.py`  
**Outcome:** agent and async execution behavior contributes to Infinity more systematically.

### Step 5 - Weight explicit feedback into KPI calculations where appropriate
**Files:** `services/infinity_service.py`, `services/infinity_loop.py`  
**Outcome:** user and system feedback affect score evolution, not just post-score decision selection.

### Step 6 - Validate the memory-weighted loop end to end
**Files:** tests covering `services/memory_scoring_service.py`, `services/infinity_orchestrator.py`, `services/infinity_loop.py`, `services/memory_capture_engine.py`  
**Outcome:** support-layer memory signals are proven to change subsequent Infinity decisions after real execution outcomes.

---

## 11. Governance Notes

* This document defines the **support layer for the Infinity Algorithm**
* All changes must align with:

  * signal flow integrity
  * closed-loop execution
* Any deviation must be documented in:

  * TECH_DEBT
  * EVOLUTION_PLAN

---

## 12. Summary (Operational Truth)

The Infinity Algorithm does not work because of formulas alone.

It works when:

> Real-world behavior is observed, converted into signals, fed into scoring, and used to continuously adjust execution.

Without the Support System:

> The Infinity Algorithm is only a measurement system.

With the Support System:

> It becomes a self-improving execution engine.

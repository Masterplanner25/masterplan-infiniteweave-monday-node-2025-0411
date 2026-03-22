# Memory Bridge — Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Memory Bridge is a **memory execution engine**: a persistence, recall, and feedback system that embeds continuity directly into AI execution.

It is not a storage layer.

It is a **memory orchestration system** designed to:

* enforce contextual continuity
* preserve authorship and identity
* improve execution through feedback-driven recall

---

## 2. Core Lifecycle (Canonical Pipeline)

```
MemoryNode → Trace → Recall → Resonance → Continuity
```

### MemoryNode

Atomic unit of memory:

* content
* tags (JSONB)
* embeddings (pgvector)
* node_type
* feedback signals (usage, success rate, weight)

---

### Trace (Critical Abstraction)

Ordered sequence of MemoryNodes representing **continuity over time**.

Defines:

* sequence
* causality
* narrative structure

Trace is the **missing link between memory and meaning**.

---

### Recall

Retrieves candidate memory using:

* semantic similarity (embeddings)
* graph relationships (links)
* trace context (sequence proximity)

---

### Resonance

Deterministic scoring pipeline combining:

* semantic similarity
* graph strength
* trace context
* recency
* feedback signals

---

### Continuity

Final stage where:

* memory is injected into execution
* execution produces new memory
* feedback updates future recall

---

## 3. Core Components

### MemoryNodes

* Stored in: `memory_nodes`
* Represent atomic memory units

---

### Traces

* Stored in:

  * `memory_traces`
  * `memory_trace_nodes`
* Represent ordered continuity structures

---

### Graph (Links)

* Stored in: `memory_links`
* Directed edges with strength
* Used for traversal and context expansion

---

### Resonance Engine

* Central scoring pipeline
* Combines all memory signals into ranked recall

---

### Memory Metrics

* Stored in: `memory_metrics`
* Captures per-run impact signals (impact_score, memory_count, avg_similarity)
* Exposed via `/memory/metrics`, `/memory/metrics/detail`, `/memory/metrics/dashboard`

---

### Execution Loop

Enforced lifecycle:

```
recall → execute → capture → feedback
```

Current implementation note:
* `runtime/memory/orchestrator.py` coordinates recall (strategy → scoring → filtering → token budget).
* `runtime/memory/memory_feedback.py` records usage/success signals.
* `runtime/execution_loop.py` wraps recall → execute → capture → feedback (pluggable executor).
* `runtime/memory/memory_learning.py` updates per-execution success_rate and low-value flags to adapt recall quality.
* `runtime/memory/memory_metrics.py` + `runtime/memory/metrics_store.py` compute and persist memory impact metrics.
* `tests/test_memory_loop_e2e.py` validates the full loop (execution → memory → recall → improved execution).

---

## 4. Architectural Layers

### Storage Layer

* PostgreSQL
* JSONB (tags)
* pgvector (embeddings)
* graph links
* trace tables

---

### Orchestration Layer

* Python / FastAPI
* DAOs
* API routes
* execution hooks
* Memory Orchestrator (recall orchestration + context building)
* Memory Feedback Engine (usage/success recording)
* Execution Loop wrapper (recall → execute → capture → feedback)
* Memory Metrics Engine (impact scoring + persistence)

---

### Engine Layer (Planned)

* Rust (PyO3)
* C++ (FFI via Rust)

Used for:

* similarity
* traversal
* scoring

---

## 5. Behavioral Guarantees

At runtime, the system guarantees:

* Every execution is memory-informed
* Every execution produces memory
* Feedback updates future recall
* Traces preserve ordered continuity
* Retrieval is explainable (resonance scoring)

---

## 6. System Classification

The Memory Bridge is:

> A hybrid memory execution engine that enforces continuity through structured memory, trace sequencing, and feedback-driven recall.

It is NOT:

* a vector database
* a RAG system
* a passive memory store

---

## 7. Evolution Plan (System Roadmap)

---

### Phase v1 — Canonical Unification (FOUNDATION)

**Goal:** Single source of truth

**Actions:**

* Remove legacy DAO (`services.memory_persistence.MemoryNodeDAO`)
* Standardize all operations on `db/dao/memory_node_dao.py`
* Eliminate dual write paths (`bridge/*` vs `/memory/*`)
* Normalize schema:

  * `node_type` (nullable vs default)
  * `tags` (JSONB consistency)
* Remove dead code (`save_memory_node`)

**Outcome:**

* Stable, predictable memory layer
* No behavioral drift between pathways

---

### Phase v2 — Trace Layer (CORE COMPLETION)

**Goal:** Implement continuity structure

**Actions:**

* Create tables:

  * `memory_traces`
  * `memory_trace_nodes`
* Implement Trace DAO
* Add API endpoints:

  * create trace
  * append to trace
  * retrieve trace
* Auto-link sequential nodes (`trace_sequence`)

**Outcome:**

* Memory becomes ordered and contextual
* Continuity becomes technically enforceable

---

### Phase v3 — Symbolic Integration

**Goal:** Unify symbolic and operational memory

**Actions:**

* Ingest:

  * `memorytraces/`
  * `memoryevents/`
  * external docs
* Convert artifacts into:

  * MemoryNodes
  * Traces
* Preserve metadata:

  * file path
  * timestamps
  * canonical IDs

**Outcome:**

* Symbolic memory becomes queryable
* Identity/continuity anchors enter runtime system

---

### Phase v4 — Resonance Engine

**Goal:** Replace ad-hoc recall with unified scoring

**Actions:**

* Build `services/resonance_engine.py`
* Combine:

  * semantic
  * graph
  * trace
  * feedback
* Integrate into DAO recall

**Outcome:**

* Deterministic, explainable memory ranking
* Improved recall quality

---

### Phase v5 — Execution Loop Enforcement

**Goal:** Make memory unavoidable

**Actions:**

* Create `services/execution_loop.py`
* Enforce:

  * recall before execution
  * capture after execution
  * automatic feedback
* Route all workflows through execution loop

**Outcome:**

* Memory becomes part of execution, not optional
* Closed-loop learning system

---

### Phase v5+ — Engine Layer (Performance)

**Goal:** High-performance memory engine

**Actions:**

* Create abstraction: `services/memory_engine.py`
* Integrate:

  * Rust (PyO3)
  * C++ (via Rust)
* Offload:

  * traversal
  * similarity
  * scoring

**Outcome:**

* Scalable, high-performance memory system
* Engine-level optimization without architecture change

---

## 8. Technical Debt (Current State)

### Structural Debt

* Dual DAO implementations
* Bridge vs memory API divergence
* Multiple memory entry points

---

### Functional Debt

* No Trace abstraction
* Weak execution loop enforcement
* Graph underutilized

---

### Conceptual Debt

* Symbolic memory disconnected from runtime
* Continuity defined but not implemented

---

## 9. Memory Bridge Phase Mapping

| Phase | Component            | Status  | Required Action    |
| ----- | -------------------- | ------- | ------------------ |
| v1    | DAO + Schema         | Partial | Unify + clean      |
| v2    | Trace Layer          | Partial | Wire into recall   |
| v3    | Symbolic Integration | Missing | Ingest + map       |
| v4    | Resonance Engine     | Partial | Replace scoring    |
| v5    | Execution Loop       | Partial | Enforce runtime    |
| v5+   | Engine Layer         | Partial | Integrate Rust/C++ |

---

## 10. Governance Notes

* This document is the **canonical reference** for Memory Bridge architecture
* All future changes must align with:

  * the lifecycle pipeline
  * single-source memory model
  * execution loop enforcement
* Any deviation must be documented in CHANGELOG and ARCHITECTURE updates

---

## 11. Summary (Operational Truth)

The Memory Bridge is not complete when it stores memory.

It is complete when:

> Memory directly shapes execution, and execution continuously reshapes memory through traceable continuity.

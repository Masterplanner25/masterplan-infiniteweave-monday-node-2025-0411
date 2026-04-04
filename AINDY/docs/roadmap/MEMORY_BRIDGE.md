# Memory Bridge - Canonical Definition & Evolution Plan

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
MemoryNode -> Trace -> Recall -> Resonance -> Continuity
```

### MemoryNode

Atomic unit of memory:

* content
* tags (JSONB)
* embeddings (pgvector)
* node_type
* causal references (`source_event_id`, `root_event_id`)
* causal scoring (`causal_depth`, `impact_score`)
* `memory_type` (`decision`, `outcome`, `failure`, `insight`)
* feedback signals (usage, success rate, weight)

---

### Trace (Critical Abstraction)

Ordered sequence of MemoryNodes representing **continuity over time**.

Defines:

* sequence
* causality
* narrative structure

Trace is the **missing link between memory and meaning**.

Current implementation note:
* Trace continuity is now complemented by execution-side causality from RippleTrace/SystemEvent, so memory can store not just sequence but source event, root cause, and downstream impact.

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
* impact weighting from causal memory

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
* Directed edges with numeric weight (legacy strength retained)
* Used for traversal and context expansion

---

### Resonance Engine

* Central scoring pipeline
* Combines all memory signals into ranked recall
* Trace-aware bonus applied when `trace_id` is provided in recall metadata

---

### Memory Metrics

* Stored in: `memory_metrics`
* Captures per-run impact signals (impact_score, memory_count, avg_similarity)
* Exposed via `/memory/metrics`, `/memory/metrics/detail`, `/memory/metrics/dashboard`

---

### Execution Loop

Enforced lifecycle:

```
recall -> execute -> capture -> feedback
```

Current implementation note:
* `runtime/memory/orchestrator.py` coordinates recall (strategy -> scoring -> filtering -> token budget).
* `runtime/memory/memory_feedback.py` records usage/success signals.
* `runtime/memory_loop.py` wraps recall -> execute -> capture -> feedback (pluggable executor).
* `runtime/memory/memory_learning.py` updates per-execution success_rate and low-value flags to adapt recall quality.
* `runtime/memory/memory_metrics.py` + `runtime/memory/metrics_store.py` compute and persist memory impact metrics.
* `tests/system/test_memory_loop_e2e.py` validates the full loop (execution -> memory -> recall -> improved execution).
* `services/memory_capture_engine.py` can now auto-capture high-impact `SystemEvent` outcomes into causal memory records and link them back into RippleTrace.

---

## 4. Architectural Layers

### Storage Layer

* PostgreSQL
* JSONB (tags)
* pgvector (embeddings, HNSW index)
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
* Execution Loop wrapper (recall -> execute -> capture -> feedback)
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

* Memory-informed execution exists for selected execution paths
* Memory-producing execution exists for selected execution paths
* Feedback updates future recall
* Traces preserve ordered continuity
* Retrieval is explainable (resonance scoring)
* High-impact execution outcomes can now be stored with explicit causal provenance

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

### Phase v1 - Canonical Unification (FOUNDATION)

**Goal:** Single source of truth

**Actions:**

* Remove legacy DAO (`memory.memory_persistence.MemoryNodeDAO`)
* Standardize all operations on `db/dao/memory_node_dao.py`
* Eliminate dual write paths (`bridge/*` vs `/memory/*`)
* Normalize schema:

  * `node_type` (nullable vs default)
  * `tags` (JSONB consistency)
* Remove dead code (`save_memory_node`)

**Outcome:**

* Stable, predictable memory layer
* No behavioral drift between pathways

**Status:** Partial

---

### Phase v2 - Trace Layer (CORE COMPLETION)

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

**Status:** Complete

---

### Phase v3 - Symbolic Integration

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

**Status:** Complete

---

### Phase v4 - Resonance Engine

**Goal:** Replace ad-hoc recall with unified scoring

**Actions:**

* Implemented scoring and ranking in `runtime/memory/scorer.py`
* Integrated into `runtime/memory/orchestrator.py` pipeline
* Combines semantic, graph, trace, recency, feedback, and impact signals

**Outcome:**

* Deterministic, explainable memory ranking
* Improved recall quality

**Status:** Complete

### Phase v4.5 - Causal Memory Integration

**Goal:** Attach meaning to memory via execution causality

**Actions:**

* add causal fields to `memory_nodes`
* auto-capture high-impact `SystemEvent` outcomes into memory
* compute `impact_score` from RippleTrace downstream span and depth
* create `stored_as_memory` edges from event -> memory node
* use impact-aware scoring during recall

**Outcome:**

* memory stores what happened, why it happened, and what it caused
* causal memory can influence future execution decisions

**Status:** Complete

---

### Phase v5 - Execution Loop Enforcement

**Goal:** Make memory unavoidable

**Actions:**

* Implemented `runtime/memory_loop.py`
* Enforced `recall -> execute -> capture -> feedback`
* Routed `/memory/execute` and workflow handlers via execution registry

**Outcome:**

* Memory becomes part of execution, not optional
* Closed-loop learning system

**Status:** Partial

---

### Phase v5+ - Engine Layer (Performance)

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

### Open Debt

* Legacy `node_type="generic"` cleanup on existing rows (migration to normalize)
* Embedding generation is synchronous on write path (latency risk)
* ✅ **Resolved:** HMAC removed from bridge write endpoints; JWT only.
* Engine Layer (Rust/C++) now integrated into runtime scoring with Python fallback; traversal-side acceleration and release-build hardening remain open
* Execution-loop enforcement is not universal across all runtime paths
* End-to-end validation for the new RippleTrace -> Memory Bridge -> Infinity path is still missing

---

## 9. Memory Bridge Phase Mapping

| Phase | Component            | Status   | Required Action        |
| ----- | -------------------- | -------- | ---------------------- |
| v1    | DAO + Schema         | Partial  | Finish canonical unification |
| v2    | Trace Layer          | Complete | Maintenance only       |
| v3    | Symbolic Integration | Complete | Maintenance only       |
| v4    | Resonance Engine     | Complete | Tune/extend as needed  |
| v4.5  | Causal Memory        | Complete | Add stronger scenario tests |
| v5    | Execution Loop       | Partial  | Expand workflow usage  |
| v5+   | Engine Layer         | Partial  | Runtime scoring integrated; traversal + release hardening remain |

---

## 10. Next Steps

### Step 1 - Finish canonical DAO unification
**Files:** `services/memory_persistence.py`, `db/dao/memory_node_dao.py`, bridge memory helper paths  
**Outcome:** all memory writes and queries use the canonical DAO without compatibility drift.

### Step 2 - Expand trace usage in recall
**Files:** `db/dao/memory_trace_dao.py`, `runtime/memory/orchestrator.py`, `runtime/memory/scorer.py`  
**Outcome:** trace context affects recall more meaningfully than a flat bonus on matching nodes.

### Step 3 - Route more execution through the memory loop
**Files:** `runtime/memory_loop.py`, `services/flow_engine.py`, `services/agent_runtime.py`  
**Outcome:** memory-informed execution becomes true for a larger share of runtime behavior.

### Step 4 - Move embeddings off the synchronous write path
**Files:** `services/embedding_service.py`, `db/dao/memory_node_dao.py`, async job plumbing if needed  
**Outcome:** memory capture latency is reduced without removing semantic retrieval.

### Step 5 - Add end-to-end causal-memory validation
**Files:** tests around `services/memory_capture_engine.py`, `services/system_event_service.py`, `services/memory_scoring_service.py`, `services/infinity_orchestrator.py`  
**Outcome:** a high-impact failure can be shown to become memory and influence a later decision path.

---

## 11. Governance Notes

* This document is the **canonical reference** for Memory Bridge architecture
* All future changes must align with:

  * the lifecycle pipeline
  * single-source memory model
  * execution loop enforcement
* Any deviation must be documented in CHANGELOG and ARCHITECTURE updates

---

## 12. Summary (Operational Truth)

The Memory Bridge is not complete when it stores memory.

It is complete when:

> Memory directly shapes execution, and execution continuously reshapes memory through traceable continuity.


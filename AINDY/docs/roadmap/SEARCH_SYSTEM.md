# Search System — Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Search System is a **multi-surface AI retrieval stack** that turns queries into ranked, actionable results across SEO analysis, lead discovery, and research workflows.

It is not a single endpoint.

It is a **search orchestration layer** intended to:

* process queries
* retrieve sources
* score relevance
* persist outcomes
* feed back into execution

---

## 2. Core Lifecycle (Canonical Pipeline)

```
Query → Processing → Retrieval → Ranking → Output
```

### Query

User or system-provided search intent:

* free text
* domain-specific templates
* task or research prompts

---

### Processing

Normalization and pre-processing:

* tokenization
* query expansion
* domain filtering

---

### Retrieval

External or internal source fetch:

* web search
* stored research results
* memory recall

---

### Ranking

Scoring and ordering:

* relevance
* fit / intent scores
* semantic similarity

---

### Output

Structured results:

* ranked leads
* SEO insights
* research summaries

---

## 3. Core Components

---

### 3.1 SEO Analysis (AI SEO)

**Implementation:**

* `routes/seo_routes.py`
* `services/seo_services.py`

**Current Capabilities:**

* keyword extraction
* readability
* keyword density
* AI meta description (`/seo/meta`)

**Missing:**

* AI SEO improvement suggestions (stubbed)
* competitor benchmarking
* AI search ranking feedback loop

---

### 3.2 Lead Generation (B2B AI Search)

**Implementation:**

* `services/leadgen_service.py`
* `routes/leadgen_router.py`
* `db/models/leadgen_model.py`

**Current Capabilities:**

* GPT-4o lead scoring
* DB persistence
* Memory Bridge logging
* Memory Orchestrator recall for prior leadgen context
* External retrieval via `modules/research_engine.web_search()` with structured response parsing + fallback

**Missing:**

* provider-backed lead search with richer parsing (current structured parsing is minimal)
* query template system (documented but not implemented)

---

### 3.3 Research / DeepSearch

**Implementation:**

* `modules/research_engine.py`
* `routes/research_results_router.py`
* `services/research_results_service.py`

**Current Capabilities:**

* research result storage
* memory logging (capture engine)
* Memory Orchestrator recall attached to `/research/query` results
* Live summary generation via `modules/research_engine.ai_analyze()`
* Live external retrieval via `modules/research_engine.web_search()`

**Missing:**

* external provider reliability/coverage guarantees (current integration is best-effort)

---

### 3.4 Memory Search (Semantic Recall)

**Implementation:**

* `routes/memory_router.py`
* `db/dao/memory_node_dao.py`

**Current Capabilities:**

* semantic similarity search (`/memory/nodes/search`)
* resonance recall (`/memory/recall`)

**Note:**

This capability exists but is not wired into the Search System flows documented under `AINDY/Search System/`.

---

## 4. Architectural Layers

### Retrieval Layer

* External search (implemented in research + leadgen flows)
* Internal search (Memory Bridge recall)

### Orchestration Layer

* FastAPI routes
* service modules

### Persistence Layer

* Postgres models for leadgen + research
* Memory Bridge for search outcomes

---

## 5. Current Implementation (Reality)

**Implemented:**

* basic SEO analysis endpoints
* lead scoring + DB persistence
* research result storage
* Memory Orchestrator recall used in LeadGen and Research query flow
* semantic memory search (separate system)
* live external retrieval in research and leadgen flow

**Missing:**

* unified search pipeline
* reusable hybrid search orchestration across search surfaces
* consistent ranking model across search surfaces (shared scorer exists, but ranking remains shallow and surface-specific)
* UI integration for SEO and LeadGen

---

## 6. System Classification

The Search System is currently:

> A fragmented set of partial search tools (SEO + LeadGen + Research) with an unintegrated semantic recall engine.

It is NOT:

* a unified search platform
* a full AI search optimization system

---

## 7. Evolution Plan (System Roadmap)

---

### Phase v1 — Stabilize Search Surfaces

**Goal:** Align live endpoints with documented behaviors

**Actions:**

* normalize SEO endpoints
* remove stubbed responses or mark them explicitly
* document leadgen retrieval integration ✅

---

### Phase v2 — Retrieval Integration

**Goal:** Enable real retrieval for leadgen + research

**Actions:**

* wire `modules/research_engine.py` into `/research/query` ✅
* replace mocked `run_ai_search()` results with real provider calls ✅
* integrate Memory Orchestrator recall into search flows ✅

---

### Phase v3 — Ranking Unification

**Goal:** Shared ranking layer

**Actions:**

* unify relevance scoring across SEO, leadgen, research (partial)

---

### Phase v4 — Feedback & Memory Loop

**Goal:** Closed-loop search system

**Actions:**

* persist outcomes to Memory Bridge
* feed results into future query weighting

---

### Phase v5 — UI + Dashboard Integration

**Goal:** Operational surface

**Actions:**

* integrate SEO + LeadGen UI into client
* add result history views

---

## 8. Technical Debt

### Structural

* search features exist in disconnected modules
* no unified query processing layer

### Functional

* ✅ leadgen search now uses real retrieval (orchestrator + provider)
* ✅ research search executes via `/research/query`
* ranking helpers are shared, but ranking remains surface-specific
* SEO suggestions stubbed

### Conceptual

* semantic search exists but is not part of Search System flows

---

## 9. Phase Mapping

| Phase | Component            | Status      | Required Action |
| ----- | -------------------- | ----------- | --------------- |
| v1    | Surface Alignment    | Partial     | Normalize       |
| v2    | Retrieval Integration| Complete    | Maintenance only |
| v3    | Ranking Unification  | Partial     | Deepen shared ranking |
| v4    | Feedback Loop        | Missing     | Persist + reuse |
| v5    | UI Integration       | Missing     | Implement       |

---

## 10. Next Steps

### Step 1 - Create a unified search service
**Files:** `services/search_service.py`  
**Outcome:** external, internal, semantic, and hybrid search requests route through one reusable interface.

### Step 2 - Standardize search request and result schemas
**Files:** `schemas/`, `routes/leadgen_router.py`, `routes/research_results_router.py`  
**Outcome:** leadgen and research return compatible ranked result structures instead of feature-specific payloads.

### Step 3 - Move hybrid retrieval into the shared search layer
**Files:** `services/leadgen_service.py`, `routes/research_results_router.py`, `services/search_service.py`  
**Outcome:** memory recall plus external retrieval is implemented once and reused across search surfaces.

### Step 4 - Add shared search history and reuse
**Files:** `db/models/leadgen_model.py`, `db/models/research_results.py`, `services/research_results_service.py`, `services/search_service.py`  
**Outcome:** search outcomes become reusable across the system instead of staying siloed by feature.

### Step 5 - Integrate unified search into agent tools
**Files:** `services/agent_tools.py`, `services/agent_runtime.py`  
**Outcome:** agents use one search contract instead of separate ad-hoc wrappers for leadgen, research, and memory recall.

### Step 6 - Expose unified search to workflow execution
**Files:** `services/flow_definitions.py`, `services/nodus_execution_service.py`  
**Outcome:** search becomes a reusable workflow capability rather than a research-only utility.

---

## 11. Governance Notes

* This document is the **canonical reference** for Search System architecture.
* Any changes must align with:

  * documented lifecycle
  * retrieval integrity
  * Memory Bridge integration rules

* Deviations must be recorded in:

  * `docs/roadmap/TECH_DEBT.md`
  * `docs/roadmap/EVOLUTION_PLAN.md`

---

## 12. Summary (Operational Truth)

The Search System is not complete when it stores results.

It is complete when:

> Queries trigger real retrieval, results are ranked and persisted, and outcomes feed back into future search behavior.

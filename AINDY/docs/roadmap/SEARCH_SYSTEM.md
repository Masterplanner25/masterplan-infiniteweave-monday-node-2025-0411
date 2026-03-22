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

**Missing:**

* routing that invokes `research_engine.web_search()`
* live external retrieval

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

* External search (planned)
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

**Missing:**

* live web search for research (provider-dependent reliability)
* unified search pipeline
* consistent ranking model across search surfaces (now shared scorer, still early)
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
* document mocked leadgen search

---

### Phase v2 — Retrieval Integration

**Goal:** Enable real retrieval for leadgen + research

**Actions:**

* wire `modules/research_engine.py` into `/research/query`
* replace mocked `run_ai_search()` results with real provider calls
* integrate Memory Orchestrator recall into search flows

---

### Phase v3 — Ranking Unification

**Goal:** Shared ranking layer

**Actions:**

* unify relevance scoring across SEO, leadgen, research (shared scorer in use)

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

* leadgen search is mocked
* research search not executed
* SEO suggestions stubbed

### Conceptual

* semantic search exists but is not part of Search System flows

---

## 9. Phase Mapping

| Phase | Component            | Status      | Required Action |
| ----- | -------------------- | ----------- | --------------- |
| v1    | Surface Alignment    | Partial     | Normalize       |
| v2    | Retrieval Integration| Partial     | Wire + replace  |
| v3    | Ranking Unification  | Partial     | Unify scoring   |
| v4    | Feedback Loop        | Missing     | Persist + reuse |
| v5    | UI Integration       | Missing     | Implement       |

---

## 10. Governance Notes

* This document is the **canonical reference** for Search System architecture.
* Any changes must align with:

  * documented lifecycle
  * retrieval integrity
  * Memory Bridge integration rules

* Deviations must be recorded in:

  * `docs/roadmap/TECH_DEBT.md`
  * `docs/roadmap/EVOLUTION_PLAN.md`

---

## 11. Summary (Operational Truth)

The Search System is not complete when it stores results.

It is complete when:

> Queries trigger real retrieval, results are ranked and persisted, and outcomes feed back into future search behavior.

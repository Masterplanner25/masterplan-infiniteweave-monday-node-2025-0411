# Social Layer — Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Social Layer is a **public-facing identity and interaction system** that captures profiles, posts, and social signals, then routes them into A.I.N.D.Y. for visibility scoring and continuity.

It is not a memory system.

It is a **social execution layer** designed to:

* represent identity
* surface content
* track interactions
* feed signals into analytics and memory

---

## 2. Core Lifecycle (Canonical Pipeline)

```
Profile → Post → Feed → Signal → Insight
```

### Profile

Identity surface:

* name
* tagline
* trust tier
* metrics snapshot

---

### Post

Content surface:

* user content
* timestamp
* visibility tier
* tags

---

### Feed

Distribution layer:

* posts surfaced by relevance
* trust-tier filtering

---

### Signal

Interaction and reaction capture:

* engagement counts
* ripple or visibility metrics

---

### Insight

Analytics + feedback:

* visibility scoring
* influence tracking
* memory capture

---

## 3. Core Components

---

### 3.1 Profiles

**Implementation:**

* `routes/social_router.py`
* `db/models/social_models.py`
* MongoDB storage

**Current Capabilities:**

* create/update profiles
* fetch profile by username

---

### 3.2 Posts + Feed

**Implementation:**

* `routes/social_router.py`
* MongoDB storage

**Current Capabilities:**

* create posts
* fetch feed with trust-tier weighted relevance scoring

--- 

### 3.3 Bridge Integration

**Implementation:**

* `routes/bridge_router.py` (`/bridge/user_event`)
* `AINDY/server.js` forwards events

**Current Capabilities:**

* Node → FastAPI bridge exists
* `/bridge/user_event` persists to SQL audit table (`bridge_user_events`)

---

### 3.4 Memory Logging

**Implementation:**

* `routes/social_router.py` calls `create_memory_node()`

**Current Capabilities:**

* posts are logged to Memory Bridge with DB session

---

### 3.5 Frontend

**Implementation:**

* `client/src/components/ProfileView.jsx`
* `client/src/components/Feed.jsx`
* `client/src/components/PostComposer.jsx`

**Current Capabilities:**

* UI surfaces for profiles + feed

---

## 4. Architectural Layers

### Storage Layer

* MongoDB (profiles, posts)

### Orchestration Layer

* FastAPI routes
* Node bridge (Express)

### Analytics Layer (Planned)

* visibility scoring
* trust-tier influence

---

## 5. Current Implementation (Reality)

**Implemented:**

* profile CRUD
* post creation
* feed listing + visibility scoring
* Node → FastAPI bridge

**Missing:**

* analytics dashboards

---

## 6. Doc → Code Parity Table

| Documented Capability | Evidence in Docs | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- | --- |
| Profile CRUD | Social layer notes | Profile create/update/read via MongoDB | Implemented | `routes/social_router.py`, `db/models/social_models.py` |
| Post creation | Social layer notes | Post insert + list | Implemented | `routes/social_router.py` |
| Feed ranking | Roadmap intent | Trust-tier weighted ranking + engagement scoring | Implemented | `routes/social_router.py` |
| Trust-tier weighting | Roadmap intent | Trust tier weighted relevance scoring in feed | Implemented | `routes/social_router.py` |
| Bridge event persistence | Bridge integration notes | `/bridge/user_event` persists to `bridge_user_events` | Implemented | `routes/bridge_router.py`, `db/models/bridge_user_event.py` |
| Memory logging | Social layer notes | Posts logged via `MemoryCaptureEngine` with DB session | Implemented | `routes/social_router.py` |
| Analytics dashboard | Roadmap intent | Not implemented | Missing | N/A |

---

## 7. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| No analytics output | No visibility metrics | `routes/social_router.py`, `client/src/components/*` |
| No analytics output | No visibility metrics | `routes/social_router.py`, `client/src/components/*` |

---

## 8. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Heuristic scoring noise | Product | Visibility scores may not reflect true relevance | Medium engagement | Medium |
| Divergent schemas | Technical | Social profile fields drift across code/docs | Inconsistent UI + data | Medium |
| Cross-system mismatch | Integration | Social signals not linked to Memory Bridge | Broken feedback loop | Medium |

---

## 9. System Classification

The Social Layer is currently:

> A social CRUD layer backed by MongoDB with visibility scoring and bridge persistence, but without analytics dashboards.

It is NOT:

* an influence graph
* a visibility ranking system
* a feedback-driven social intelligence layer

---

## 10. Evolution Plan (System Roadmap)

---

### Phase v1 — Stabilize Social CRUD

**Goal:** Stable identity and content flow

**Actions:**

* normalize profile schema
* harden post creation + feed response

---

### Phase v2 — Bridge Persistence

**Goal:** Make bridge events real

**Actions:**

* persist `/bridge/user_event` ✅

---

### Phase v3 — Visibility Scoring

**Goal:** Ranking logic

**Actions:**

* trust-tier weighting ✅
* engagement-based ordering ✅

---

### Phase v4 — Analytics Layer

**Goal:** Social intelligence surface

**Actions:**

* dashboards
* visibility metrics

---

### Phase v5 — Feedback Loop

**Goal:** Continuous improvement

**Actions:**

* feed analytics into scoring
* log visibility outcomes to Memory Bridge

---

## 11. Technical Debt

### Structural

* analytics persistence not defined for visibility metrics

### Functional

* analytics dashboards not implemented

### Conceptual

* visibility graph and analytics absent

---

## 12. Phase Mapping

| Phase | Component           | Status      | Required Action |
| ----- | ------------------- | ----------- | --------------- |
| v1    | CRUD + Feed         | Implemented | Stabilize       |
| v2    | Bridge Persistence  | Implemented | Persisted       |
| v3    | Visibility Scoring  | Implemented | Ranked          |
| v4    | Analytics Layer     | Missing     | Build           |
| v5    | Feedback Loop       | Missing     | Connect         |

---

## 13. Governance Notes

* This document is the **canonical reference** for the Social Layer.
* Any deviations must be recorded in:

  * `docs/roadmap/TECH_DEBT.md`
  * `docs/roadmap/EVOLUTION_PLAN.md`

---

## 14. Summary (Operational Truth)

The Social Layer is not complete when posts are stored.

It is complete when:

> Social activity produces visibility signals, those signals affect ranking, and outcomes are captured as memory and analytics.

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
* fetch feed (most recent)

**Missing:**

* trust-tier weighted ranking
* visibility scoring

---

### 3.3 Bridge Integration

**Implementation:**

* `routes/bridge_router.py` (`/bridge/user_event`)
* `AINDY/server.js` forwards events

**Current Capabilities:**

* Node → FastAPI bridge exists

**Missing:**

* persistence of user_event data

---

### 3.4 Memory Logging

**Implementation:**

* `routes/social_router.py` calls `create_memory_node()`

**Current Capabilities:**

* attempt to log social posts

**Missing:**

* DB session passed → logs are non-persistent

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
* feed listing
* Node → FastAPI bridge

**Missing:**

* visibility scoring
* trust-tier weighting
* analytics dashboards
* persistent bridge event logging
* persistent memory logging

---

## 6. Doc → Code Parity Table

| Documented Capability | Evidence in Docs | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- | --- |
| Profile CRUD | Social layer notes | Profile create/update/read via MongoDB | Implemented | `routes/social_router.py`, `db/models/social_models.py` |
| Post creation | Social layer notes | Post insert + list | Implemented | `routes/social_router.py` |
| Feed ranking | Roadmap intent | No ranking or scoring | Missing | `routes/social_router.py` |
| Trust-tier weighting | Roadmap intent | Trust tier exists but unused in ranking | Missing | `db/models/social_models.py` |
| Bridge event persistence | Bridge integration notes | `/bridge/user_event` exists but not persisted | Missing | `routes/bridge_router.py` |
| Memory logging | Social layer notes | `create_memory_node()` called without DB session | Partial (non-persistent) | `routes/social_router.py` |
| Analytics dashboard | Roadmap intent | Not implemented | Missing | N/A |

---

## 7. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| Bridge events not persisted | User events lost, no audit trail | `routes/bridge_router.py`, `db/models/social_models.py` |
| Memory logging non-persistent | Social activity not captured in Memory Bridge | `routes/social_router.py`, `services/memory_service.py` |
| No feed ranking | Feed is chronological only | `routes/social_router.py` |
| No trust-tier weighting | Trust tier has no operational effect | `routes/social_router.py`, `db/models/social_models.py` |
| No analytics output | No visibility metrics | `routes/social_router.py`, `client/src/components/*` |

---

## 8. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Silent loss of user_event | Data integrity | Bridge payload accepted but not stored | Observability gap | High |
| Social activity not in memory | Continuity | Posts never captured as memory | Loss of longitudinal signal | High |
| Flat feed reduces relevance | Product | No ranking or trust tier impact | Low engagement | Medium |
| Divergent schemas | Technical | Social profile fields drift across code/docs | Inconsistent UI + data | Medium |
| Cross-system mismatch | Integration | Social signals not linked to Memory Bridge | Broken feedback loop | Medium |

---

## 9. System Classification

The Social Layer is currently:

> A basic social CRUD layer backed by MongoDB, without visibility scoring or analytics.

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

* persist `/bridge/user_event`
* add audit table or memory capture

---

### Phase v3 — Visibility Scoring

**Goal:** Ranking logic

**Actions:**

* trust-tier weighting
* engagement-based ordering

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

* bridge endpoint does not persist events

### Functional

* feed has no ranking or scoring
* memory logging is non-persistent

### Conceptual

* visibility graph and analytics absent

---

## 12. Phase Mapping

| Phase | Component           | Status      | Required Action |
| ----- | ------------------- | ----------- | --------------- |
| v1    | CRUD + Feed         | Implemented | Stabilize       |
| v2    | Bridge Persistence  | Missing     | Persist         |
| v3    | Visibility Scoring  | Missing     | Rank            |
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

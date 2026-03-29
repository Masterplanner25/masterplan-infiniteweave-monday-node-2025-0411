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
* track impressions and interaction signals
* expose social analytics summaries

**Missing:**

* comment/reply model

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
* analytics panel and top-performing content summaries

---

## 4. Architectural Layers

### Storage Layer

* MongoDB (profiles, posts)

### Orchestration Layer

* FastAPI routes
* Node bridge (Express)

### Analytics Layer

* visibility scoring
* trust-tier influence
* engagement and conversion summaries

---

## 5. Current Implementation (Reality)

**Implemented:**

* profile upsert + fetch
* post creation
* feed listing + visibility scoring
* Node → FastAPI bridge
* analytics summaries and trend output
* memory-backed performance feedback
* Infinity-facing social performance signals

**Missing:**

* social narrative or event-driven feed surfaces
* comment/reply model

---

## 6. Doc → Code Parity Table

| Documented Capability | Evidence in Docs | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- | --- |
| Profile CRUD | Social layer notes | Profile upsert + public fetch via MongoDB | Partial | `routes/social_router.py`, `db/models/social_models.py` |
| Post creation | Social layer notes | Post insert + list | Implemented | `routes/social_router.py` |
| Feed ranking | Roadmap intent | Trust-tier weighted ranking + Infinity score weighting | Implemented | `routes/social_router.py` |
| Trust-tier weighting | Roadmap intent | Trust tier weighted relevance scoring in feed | Implemented | `routes/social_router.py` |
| Bridge event persistence | Bridge integration notes | `/bridge/user_event` persists to `bridge_user_events` | Implemented | `routes/bridge_router.py`, `db/models/bridge_user_event.py` |
| Memory logging | Social layer notes | Posts logged via `MemoryCaptureEngine` with DB session | Implemented | `routes/social_router.py` |
| Interactions (likes/comments/boosts) | Social layer intent | Interaction tracking exists for views/clicks/engagement, but comment/reply flows are still absent | Partial | `db/models/social_models.py`, `routes/social_router.py` |
| Analytics dashboard | Roadmap intent | Analytics summaries, trends, and top content are exposed in API/UI | Implemented | `routes/social_router.py`, `client/src/components/Feed.jsx` |

---

## 7. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| No comment/reply model | Social layer still lacks threaded discussion | `routes/social_router.py`, `db/models/social_models.py`, `client/src/components/*` |
| Identity split between social and system identity | Profile state can drift across Mongo social profiles and SQL identity profiles | `routes/social_router.py`, `routes/identity_router.py`, identity service/model files |

---

## 8. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Heuristic scoring noise | Product | Visibility scores may not reflect true relevance | Medium engagement | Medium |
| Divergent schemas | Technical | Social profile fields drift across code/docs | Inconsistent UI + data | Medium |
| Cross-system mismatch | Integration | Social signals are linked to Memory Bridge, but identity/profile state can still drift across systems | Inconsistent behavior and analytics context | Medium |

---

## 9. System Classification

The Social Layer is currently:

> A social interaction and analytics layer backed by MongoDB with visibility scoring, performance feedback, and bridge persistence, but without threaded discussion or broader narrative surfaces.

It is NOT:

* an influence graph
* a complete narrative/event-driven social system

---

## 10. Evolution Plan (System Roadmap)

---

### Phase v1 — Stabilize Social CRUD

**Goal:** Stable identity and content flow

**Actions:**

* normalize profile schema
* harden post creation + feed response

**Status:** Complete

---

### Phase v2 — Bridge Persistence

**Goal:** Make bridge events real

**Actions:**

* persist `/bridge/user_event` ✅

**Status:** Complete

---

### Phase v3 — Visibility Scoring

**Goal:** Ranking logic

**Actions:**

* trust-tier weighting ✅
* engagement-based ordering ✅

**Status:** Complete

---

### Phase v4 — Analytics Layer

**Goal:** Social intelligence surface

**Actions:**

* dashboards ✅
* visibility metrics ✅

---

### Phase v5 — Feedback Loop

**Goal:** Continuous improvement

**Actions:**

* feed analytics into scoring ✅
* log visibility outcomes to Memory Bridge ✅

---

## 11. Technical Debt

### Structural

* analytics persistence is currently embedded in post documents rather than a separate history model

### Functional

* comment/reply support is not implemented

### Conceptual

* social profile and system identity remain separate layers

---

## 12. Phase Mapping

| Phase | Component           | Status      | Required Action |
| ----- | ------------------- | ----------- | --------------- |
| v1    | CRUD + Feed         | Complete    | Maintenance only |
| v2    | Bridge Persistence  | Complete    | Maintenance only |
| v3    | Visibility Scoring  | Complete    | Maintenance only |
| v4    | Analytics Layer     | Complete    | Maintenance only |
| v5    | Feedback Loop       | Complete    | Maintenance only |

---

## 13. Next Steps

### Step 1 - Add interaction endpoints
**Files:** `routes/social_router.py`, `db/models/social_models.py`  
**Outcome:** likes, boosts, and comments become real persisted interactions instead of dormant fields on posts.

### Step 2 - Add a comment and reply model
**Files:** `db/models/social_models.py`, `routes/social_router.py`, `client/src/components/Feed.jsx`  
**Outcome:** the social layer supports actual discussion threads instead of one-way posting only.

### Step 3 - Add a comment and reply model
**Files:** `db/models/social_models.py`, `routes/social_router.py`, `client/src/components/Feed.jsx`  
**Outcome:** the social layer supports threaded discussion instead of only post-level interactions.

### Step 4 - Unify social profile with system identity
**Files:** `routes/social_router.py`, `routes/identity_router.py`, identity service/model files  
**Outcome:** Mongo social profiles and SQL identity profiles stop drifting as separate user identity systems.

### Step 5 - Surface bridge and system-origin events where intended
**Files:** `routes/bridge_router.py`, `routes/social_router.py`, `client/src/components/Feed.jsx`  
**Outcome:** bridge-origin or system-origin events can appear in the social layer instead of remaining isolated audit rows.

### Step 6 - Expand analytics history and retention
**Files:** `db/models/social_models.py`, `routes/social_router.py`, analytics UI components  
**Outcome:** trend analysis is based on durable history rather than only current post-document counters.

---

## 14. Governance Notes

* This document is the **canonical reference** for the Social Layer.
* Any deviations must be recorded in:

  * `docs/roadmap/TECH_DEBT.md`
  * `docs/roadmap/EVOLUTION_PLAN.md`

---

## 15. Summary (Operational Truth)

The Social Layer is not complete when posts are stored.

It is complete when:

> Social activity produces visibility signals, those signals affect ranking, and outcomes are captured as memory and analytics.

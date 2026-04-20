# 🌐 Masterplan Infinite Weave: A.I.N.D.Y.
### The AI-First Social Operating System

> **"The resume is dead. Long live Velocity."**

**Masterplan Infinite Weave (MPIW)** is a living, AI-native knowledge and execution ecosystem.
**A.I.N.D.Y.** (Augmented Intelligence Network for Development & Yield) is the operational core that transforms that knowledge into measurable execution.

This repository represents the **v1.0 Release**: The full convergence of the Execution Engine, the Memory Scribe, and the Trust-Based Social Layer.

---

## 🧠 The Philosophy: "Anti-LinkedIn"

Traditional platforms reward *performance* (posting). A.I.N.D.Y. rewards *execution* (building).

1.  **Proof of Velocity:** Your profile isn't a static resume. It is a live dashboard of your **TWR (Time-to-Wealth Ratio)** and **Execution Velocity**, updated automatically as you complete tasks.
2.  **Trust Tiers:** No more "1st/2nd/3rd connections." Relationships are defined by **Trust** (Inner Circle, Collaborator, Observer).
3.  **The Memory Scribe:** You don't document your life; the AI does. Every social broadcast is automatically logged into a symbolic memory structure for long-term retrieval.

---

## 🧬 Ecosystem Architecture

A.I.N.D.Y. runs on a **Hybrid Intelligence Stack**:

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | **React + Vite** | The Interface (Dashboard, Profile, Feed, Composer). |
| **Backend** | **FastAPI (Python)** | Modular API handling routing, logic, and background threads. |
| **Metrics DB** | **PostgreSQL (SQLAlchemy)** | Stores structured data: Tasks, TWR Scores, Financial Metrics. |
| **Social DB** | **MongoDB** | Stores flexible data: User Profiles, Feeds, Posts, Trust Graphs. |
| **Intelligence** | **OpenAI + Symbolic Bridge** | The "Brain" that analyzes text and stores long-term memory nodes. |

---

## 🚀 Features Live in v1.0

### 1. The Velocity Engine
* **Task Dashboard:** Create, Start, and Complete tasks.
* **Auto-Calculation:** Completing a task triggers a TWR calculation based on complexity vs. time spent.
* **Profile Sync:** Completion events automatically update your public **Execution Velocity** score in the Social Layer.

### 2. The Trust Feed (Social Layer)
* **Post Composer:** Broadcast updates to specific audiences.
* **Trust Selectors:** Choose visibility: `🌍 Public`, `🤝 Partners`, or `🔒 Inner Circle`.
* **Live Feed:** A chronological stream of verified network activity.

### 3. The Memory Scribe
* **Auto-Documentation:** Every post sent to the Social Layer is simultaneously "teleported" to the **Bridge**.
* **Symbolic Storage:** The AI creates a `MemoryNode` referencing the post, ensuring it "remembers" your context forever.

### 4. Identity Nodes
* **Live Profile:** Displays Username, Tagline, and Bio.
* **Metrics Visualization:** Real-time display of TWR Score and Velocity.

---

## 🛠️ Installation & Setup

### Prerequisites
* Python 3.10+
* Node.js 18+
* MongoDB (Local Community Edition or Atlas)

### 1. Start the Backend (The Brain)
```powershell
cd AINDY
uvicorn main:app --reload

Server runs at: http://127.0.0.1:8000

Start the Frontend (The Face)
cd client
npm run dev

Client runs at: http://localhost:5173

A.I.N.D.Y/
├── AINDY/                  # BACKEND (Python)
│   ├── bridge/             # The link between AI Memory and Database
│   ├── db/                 # Database configurations (SQL + Mongo)
│   │   ├── models/         # Data Models (Social, Metrics, Tasks)
│   │   ├── mongo_setup.py  # MongoDB Connection
│   │   └── database.py     # PostgreSQL Connection
│   ├── routes/             # API Endpoints (social, tasks, arm)
│   ├── services/           # Business Logic (Calculations, Scribe)
│   └── main.py             # Application Entry Point
│
├── client/                 # FRONTEND (React)
│   ├── src/
│   │   ├── api.js          # API Bridge functions
│   │   ├── components/     # UI Modules (Feed, Profile, TaskDash)
│   │   └── App.jsx         # Main Router & Sidebar

Author
Shawn Knight Meta-Architect • Founder of The Masterplan Infinite Weave

Medium: Masterplan Infinite Weave Publication

LinkedIn: @masterplaninfiniteweave

GitHub: @Masterplanner25

© 2025 Shawn Knight · Masterplan Infinite Weave


[![CI](https://github.com/Masterplanner25/masterplan-infiniteweave-monday-node-2025-0411/actions/workflows/ci.yml/badge.svg)](https://github.com/Masterplanner25/masterplan-infiniteweave-monday-node-2025-0411/actions/workflows/ci.yml)

---

## Platform

A.I.N.D.Y. is a FastAPI-based platform backend for versioned syscalls, Nodus
execution, memory retrieval and persistence, flow orchestration, agent runs, and
execution observability.

The release-facing entrypoints are the public health routes, the auth routes,
and the `/platform/*` surface. The platform surface exposes:

- platform API key management
- syscall discovery and dispatch
- dynamic flow and node registration
- Nodus script execution, trace lookup, and scheduling
- tenant usage and memory address space queries
- OS-level attention monitoring via the [Watcher](docs/watcher/index.md)

## Documentation

| | |
|---|---|
| [Getting Started](docs/getting-started/index.md) | Up and running in 5 minutes |
| [Syscall System](docs/runtime/SYSCALL_SYSTEM.md) | Versioned syscall layer, ABI contracts |
| [System Spec](docs/architecture/SYSTEM_SPEC.md) | Top-level system specification |
| [Runtime Behavior](docs/runtime/RUNTIME_BEHAVIOR.md) | Scheduler, event bus, execution modes |
| [Execution Contract](docs/runtime/EXECUTION_CONTRACT.md) | What the flow engine guarantees |
| [OS Isolation Layer](docs/runtime/OS_ISOLATION_LAYER.md) | Tenant isolation and quota enforcement |
| [Plugin Registry Pattern](docs/architecture/PLUGIN_REGISTRY_PATTERN.md) | How apps integrate with the runtime |
| [API Contracts](docs/platform/interfaces/API_CONTRACTS.md) | Endpoint and component contracts |
| [Testing Strategy](docs/platform/engineering/TESTING_STRATEGY.md) | Test suite structure and coverage targets |
| [AINDY Internals](docs/architecture/AINDY_INTERNALS.md) | Directory structure and runtime notes |
| [Full Docs](docs/index.md) | Complete documentation index |

---

### Legacy Note

Earlier experimental builds (Memory Bridge v1, RippleTrace MVP, initial A.I.N.D.Y. prototypes)
are preserved in the `/legacy` folder for historical and educational purposes.
Current development continues under `/AINDY` (backend) and `/MemoryBridge` (symbolic layer).



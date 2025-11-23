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


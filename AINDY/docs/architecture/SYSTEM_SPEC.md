# SYSTEM_SPEC

This document is the authoritative, agent-facing specification for the `masterplan-infiniteweave-monday-node-2025-0411` repository. It is intentionally architectural and safety-focused.

## 1. High-Level System Purpose
- Provide the A.I.N.D.Y. backend as the operational execution layer for Masterplan Infinite Weave, including task execution, metrics, memory persistence, research logging, and system governance hooks.
- Expose a FastAPI API that supports:
  - AI-assisted “Genesis” masterplan creation and lifecycle management.
  - Memory Bridge persistence and symbolic trace logging.
  - RippleTrace visibility events.
  - Task execution and analytics/metrics calculations.
  - Auxiliary subsystems (ARM/DeepSeek analysis, leadgen, social/network events).

Primary backend entry point: `AINDY/main.py`.

## 2. Architectural Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  (React/Vite — client/)                           │
│  ProfileView · Feed · PostComposer · TaskDashboard          │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP / REST
┌───────────────────────▼─────────────────────────────────────┐
│  Node/Express Gateway  (AINDY/server.js)                    │
│  /api/users → POST /network_bridge/connect                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│  FastAPI Application  (AINDY/main.py)                       │
│  18 routers · daemon background tasks · CORS middleware     │
│  ⚠ No auth middleware (see docs/roadmap/TECH_DEBT.md §6)    │
└──────┬────────────────┬────────────────┬────────────────────┘
       │                │                │
┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────────────────┐
│  Services   │  │   Routes    │  │  Memory Bridge          │
│  (AINDY/    │  │  /tasks     │  │  bridge_router.py       │
│  services/) │  │  /social    │  │  (/bridge/*)            │
│             │  │  /analytics │  │  HMAC permission model  │
│  C++ kernel │  │  /bridge    │  │  → MemoryNodeDAO        │
│  (via Rust  │  │  /research  │  │  → memory_nodes table   │
│  PyO3)      │  │  /genesis   │  └────────────────────────┘
│             │  │  … 13 more  │
└──────┬──────┘  └──────┬──────┘
       │                │
┌──────▼─────────────────▼──────────────────────────────────┐
│  Data Layer                                                │
│  PostgreSQL (SQLAlchemy)         MongoDB (motor/pymongo)   │
│  ├── tasks                       └── social posts          │
│  ├── memory_nodes (UUID/JSONB)       profiles              │
│  ├── memory_links                                          │
│  ├── calculation_results                                   │
│  ├── research_results                                      │
│  ├── master_plans / genesis_sessions                       │
│  └── … (17 total ORM models)                               │
└────────────────────────────────────────────────────────────┘
       │
┌──────▼────────────────────────────────────────────────────┐
│  C++ Semantic Kernel  (bridge/memory_bridge_rs/)           │
│  Python → Rust (PyO3) → C++ (extern "C" FFI)              │
│  cosine_similarity · weighted_dot_product                  │
│  Build: cc crate + MSVC VS 2022 x64                        │
│  Status: debug build (release blocked by AppControl)       │
└───────────────────────────────────────────────────────────┘
```

**Frontend**
- React + Vite client in `client/` with API calls in `client/src/api.js`.
- Hardcoded local API base: `http://127.0.0.1:8000`.

**Gateway**
- Node/Express gateway in `AINDY/server.js`.
- Accepts `/api/users` and forwards a handshake to the backend at `/network_bridge/connect`.

**Backend**
- FastAPI app (`AINDY/main.py`) with routers composed in `AINDY/routes/__init__.py`.
- Core configuration and runtime environment in `AINDY/config.py`.
- Domain logic in `AINDY/services/`.
- Data models in `AINDY/db/models/`.
- Pydantic schemas in `AINDY/schemas/`.

**Databases**
- Primary relational DB: PostgreSQL (enforced by `AINDY/config.py`).
- SQLAlchemy engine/session in `AINDY/db/database.py`.
- MongoDB for the social layer (used in `AINDY/services/task_services.py` via `AINDY/db/mongo_setup.py`).

**Memory Bridge**
- Database-backed memory nodes and links in `AINDY/services/memory_persistence.py`.
- FastAPI interface in `AINDY/routes/bridge_router.py` with signed permissions.
- Symbolic, file-based traces in `AINDY/memoryevents/` and `AINDY/memorytraces/`.

**C++ Semantic Kernel**
- High-performance vector math exposed to Python via a Rust/PyO3 extension (`AINDY/bridge/memory_bridge_rs/`).
- Implements `cosine_similarity` and `weighted_dot_product` in C++ (`memory_cpp/semantic.cpp`).
- Rust `extern "C"` FFI layer in `src/cpp_bridge.rs`; PyO3 bindings in `src/lib.rs`.
- Python fallback in `AINDY/services/calculation_services.py` (app works without compiled extension).
- Build: `cc` crate compiles C++ via MSVC VS 2022 x64 (no proc-macros, compatible with AppControl).

**Background Tasks**
- Startup daemon threads in `AINDY/main.py` (recurrence and reminders stubs).
- Long-running loops in `AINDY/services/task_services.py` (`check_reminders`, `handle_recurrence`), each creating its own DB sessions.

## 3. Data Flow Between Layers

**Frontend → Backend**
- `client/src/api.js` issues HTTP requests to FastAPI endpoints (e.g., `/research/query`, `/arm/*`, `/tasks/*`, `/social/*`, `/leadgen`).

**Gateway → Backend**
- `AINDY/server.js` forwards a user handshake to `POST /network_bridge/connect` with fields:
  - `author_name`, `platform`, `connection_type`, `notes`.

**Backend → Databases**
- PostgreSQL receives all core domain persistence via SQLAlchemy models.
- MongoDB receives social-layer updates (task completion updates a profile metric snapshot).

**Backend ↔ Memory Bridge**
- `POST /bridge/nodes` creates memory nodes in `memory_nodes` table.
- `POST /bridge/link` creates link edges in `memory_links`.
- `GET /bridge/nodes` queries memory nodes by tags.

**Backend ↔ External Model Providers**
- OpenAI Chat Completions via `AINDY/services/genesis_ai.py`.
- DeepSeek tooling is invoked via `AINDY/services/deepseek_arm_service.py` (modules in `AINDY/modules/deepseek/`).

### Detailed Flow Paths

**Task → Velocity → Profile loop (Social Layer)**
```
POST /tasks/complete
  └─► task_services.py: mark task complete → PostgreSQL tasks
        └─► MongoDB profiles: $inc execution_velocity, $inc twr_score, $set updated_at
              └─► bridge.py: create_memory_node()
                    └─► ⚠ writes CalculationResult (wrong table — see TECH_DEBT §2)
```

**Memory Node creation (correct path via bridge_router)**
```
POST /bridge/nodes
  └─► bridge_router.py: verify_permission_or_403() (HMAC + TTL check)
        └─► MemoryNodeDAO.save_memory_node()  (memory_persistence.py)
              └─► INSERT INTO memory_nodes (UUID, content, tags, node_type, extra)
                    └─► RippleTrace event emitted
```

**Engagement Score calculation (C++ kernel path)**
```
POST /analytics/engagement  (or any route invoking calculate_engagement_score)
  └─► calculation_services.py: calculate_engagement_score()
        └─► _cpp_weighted_dot([likes, shares, comments, clicks, time_on_page],
                               [2.0, 3.0, 1.5, 1.0, 0.5])
              └─► Rust: weighted_dot_product() — lib.rs PyO3 binding
                    └─► C++: weighted_dot_product() — semantic.cpp
                          └─► Python fallback if extension not loaded
```

## 4. Session Isolation Rules
- Each API request must use its own SQLAlchemy session from `get_db()` in `AINDY/db/database.py`.
- Never share a `Session` between requests, threads, or async tasks.
- Background loops (e.g., reminder/recurrence) must create and close their own sessions.
- MongoDB client is a process-level singleton; do not create per-request clients (`AINDY/db/mongo_setup.py`).

## 5. Model and Database Boundaries
- SQLAlchemy ORM models live in `AINDY/db/models/*.py`.
- Pydantic request/response schemas live in `AINDY/schemas/*.py` and route-local BaseModels.
- Service functions should accept a SQLAlchemy `Session` and operate only through ORM models.
- The Memory Bridge tables (`memory_nodes`, `memory_links`) are separate from symbolic filesystem traces.

## 6. Invariants That Must Not Be Broken
- **PostgreSQL requirement**: `DATABASE_URL` must be a PostgreSQL URI (enforced in `AINDY/config.py`).
- **UTC timestamps**: DB connections enforce UTC via `AINDY/db/database.py`.
- **Genesis session locking**: a `GenesisSessionDB` cannot be re-locked or re-used once status is `locked` (`AINDY/services/masterplan_factory.py`).
- **Single active masterplan**: activating a plan must deactivate all others (`AINDY/routes/genesis_router.py`).
- **Memory link uniqueness**: `memory_links` must be unique on `(source, target, link_type)` (`AINDY/services/memory_persistence.py`).
- **Bridge permissions**: memory bridge mutations (`/bridge/nodes`, `/bridge/link`) require a valid HMAC signature and TTL (`AINDY/routes/bridge_router.py`).

## 7. Integration Contracts Between Components

**Frontend API Contract**
- `client/src/api.js` expects JSON responses or raw text; backend must not return HTML error pages for API routes.
- Long-running ARM operations should return a JSON response with result summaries.

**Gateway Contract**
- `/network_bridge/connect` accepts:
  - `author_name` (string, required)
  - `platform` (string, required)
  - `connection_type` (string, default `BridgeHandshake`)
  - `notes` (string, optional)

**Memory Bridge Contract**
- `POST /bridge/nodes` payload:
  - `content`, `tags`, `node_type`, `extra`, and `permission` (HMAC signature).
- `POST /bridge/link` payload:
  - `source_id`, `target_id`, `link_type`, and `permission`.

**Genesis Contract**
- `/genesis/session` creates a session with a structured `summarized_state`.
- `/genesis/message` expects `session_id` and `message`, returns a JSON with `reply`, `state_update`, `synthesis_ready`.

**Model Provider Contract**
- `AINDY/services/genesis_ai.py` expects OpenAI to return a valid JSON payload.
- If parsing fails, it must return a safe fallback (current behavior).

## 8. Concurrency Considerations
- SQLAlchemy engine is configured with connection pooling (`pool_size=10`, `max_overflow=20`).
- Background threads in `AINDY/main.py` are daemon threads; they must not block app startup.
- Never use a SQLAlchemy session across threads. Create a new session per thread/task.
- Avoid blocking event loop in FastAPI routes; long-running work should move to background tasks or services.

## 9. Migration and Schema Rules
- Alembic is the source of truth for schema evolution (`AINDY/alembic/`).
- Every new ORM model change must have a matching Alembic migration in `AINDY/alembic/versions/`.
- Do not edit existing migrations once applied; create new migrations for changes.
- If you add a new table or column, update:
  - ORM model in `AINDY/db/models/`
  - Pydantic schema (if exposed)
  - Alembic migration

## 10. Testing and Validation Expectations
- Unit and route tests should exist for new business logic.
- Existing tests live at:
  - Root: `test_*.py`
  - Backend: `AINDY/tests/`
- Validate DB migrations locally before merging:
  - `alembic upgrade head` in the `AINDY/` directory.
- Validate API contracts against `client/src/api.js` and `AINDY/routes/*`.

## Known Gaps/Tech Debt
- Frontend `client/` is a template baseline with limited domain UI; contracts may evolve rapidly.
- `AINDY/server.js` gateway uses an in-memory user list and lacks persistence and auth.
- Background tasks in `AINDY/main.py` are stubs and not using a formal scheduler/queue.
- `AINDY/services/memory_persistence.py` includes an orphan `save_memory_node(self, memory_node)` at module level (takes `self` but is not a class method; dead code that raises `TypeError` if called).
- There is no standardized test suite coverage across routers/services; most tests are minimal.
- `AINDY/bridge/bridge.py::create_memory_node()` writes to `calculation_results` (wrong table); content and tags are silently discarded. See `docs/roadmap/TECH_DEBT.md` §2 for fix path.
- No authentication or authorization middleware on any FastAPI route. HMAC protection covers only `POST /bridge/nodes` and `POST /bridge/link`.
- C++ semantic kernel (`bridge/memory_bridge_rs/`) is built in debug mode only; `MemoryNode` has no vector embeddings, making semantic search inoperable. See `docs/roadmap/TECH_DEBT.md` §8.

Full inventory: `docs/roadmap/TECH_DEBT.md`.

## Notes for AI Agents
- Prefer edits in `AINDY/services/` for domain logic and `AINDY/routes/` for HTTP contracts.
- Avoid introducing new cross-module state. Use dependency injection (FastAPI `Depends`) and per-request sessions.
- Keep symbolic memory files (`AINDY/memoryevents/`, `AINDY/memorytraces/`) unchanged unless explicitly asked.

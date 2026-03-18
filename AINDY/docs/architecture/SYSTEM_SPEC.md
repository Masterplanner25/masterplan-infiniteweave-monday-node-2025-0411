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
│  19 routers · daemon background tasks · CORS middleware     │
│  JWT auth · API key auth · SlowAPI rate limiting            │
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
│  ├── users                                                 │
│  └── … (18 total ORM models)                               │
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
- Sends `X-API-Key` header (read from `AINDY_API_KEY` env var via `dotenv`) on all FastAPI calls.

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
- FastAPI interface split across two routers:
  - `AINDY/routes/bridge_router.py` — HMAC-signed legacy write interface (`/bridge/*`).
  - `AINDY/routes/memory_router.py` — JWT-authenticated read/write/search interface (`/memory/*`).
- Canonical DAO: `AINDY/db/dao/memory_node_dao.py` (`MemoryNodeDAO`).
- Embedding pipeline (Phase 2): `AINDY/services/embedding_service.py` generates OpenAI `text-embedding-ada-002` vectors (1536 dims) on every `MemoryNodeDAO.save()` call. Zero-vector fallback on failure.
- Semantic retrieval (Phase 2): `MemoryNodeDAO.find_similar()` uses pgvector `<=>` cosine distance. `MemoryNodeDAO.recall()` applies resonance scoring: `(semantic * 0.6) + (tag * 0.2) + (recency * 0.2)`.
- C++ kernel: `bridge/memory_bridge_rs/target/debug/memory_bridge_rs` provides `semantic_similarity()` via PyO3. Used in `embedding_service.cosine_similarity()` with Python fallback.
- Node type enforcement: `VALID_NODE_TYPES = {"decision", "outcome", "insight", "relationship"}` enforced via SQLAlchemy event listener.
- Symbolic, file-based traces in `AINDY/memoryevents/` and `AINDY/memorytraces/` (not referenced by API code).

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
- `POST /bridge/nodes` creates memory nodes via HMAC-authenticated `bridge_router.py`.
- `POST /bridge/link` creates link edges in `memory_links`.
- `GET /bridge/nodes` queries memory nodes by tags.
- `POST /memory/nodes` creates memory nodes via JWT auth; generates and stores embedding via `embedding_service.py`.
- `GET /memory/nodes/{id}` retrieves a node by UUID.
- `GET /memory/nodes/{id}/links` retrieves graph neighbors.
- `GET /memory/nodes` tag-based search.
- `POST /memory/nodes/search` semantic similarity search via pgvector (`<=>` cosine distance).
- `POST /memory/recall` resonance-scored retrieval: `(semantic*0.6) + (tag*0.2) + (recency*0.2)`.
- `POST /memory/links` creates directed links.

**Backend ↔ External Model Providers**
- OpenAI Chat Completions via `AINDY/services/genesis_ai.py`.
- DeepSeek tooling is invoked via `AINDY/services/deepseek_arm_service.py` (modules in `AINDY/modules/deepseek/`).

### Detailed Flow Paths

**Task → Velocity → Profile loop + Memory (Social Layer — Phase 3)**
```
task_services.complete_task(db, name, user_id)
  └─► mark task complete → PostgreSQL tasks [db.commit()]
  └─► MongoDB profiles: $inc execution_velocity, $inc twr_score (fire-and-forget)
  └─► bridge.create_memory_node(node_type="outcome", tags=["task","completion"])
        └─► MemoryNodeDAO.save() → embedding_service.generate_embedding() → OpenAI ada-002
              └─► INSERT INTO memory_nodes (content, node_type, user_id, embedding)
        (fire-and-forget: exception silenced, task completion unaffected)
```

**Memory Node creation via bridge_router (HMAC path)**
```
POST /bridge/nodes
  └─► bridge_router.py: verify_permission_or_403() (HMAC + TTL check)
        └─► MemoryNodeDAO.save_memory_node()  (memory_persistence.py)
              └─► INSERT INTO memory_nodes (UUID, content, tags, node_type, extra)
```

**Memory Node creation via memory_router (JWT path — Phase 2)**
```
POST /memory/nodes
  └─► memory_router.py: Depends(get_current_user) (JWT check)
        └─► MemoryNodeDAO.save()  (db/dao/memory_node_dao.py)
              └─► embedding_service.generate_embedding()
                    └─► OpenAI text-embedding-ada-002 → [float * 1536]
              └─► INSERT INTO memory_nodes (UUID, content, tags, node_type, user_id, embedding)

POST /memory/recall
  └─► memory_router.py: Depends(get_current_user)
        └─► embedding_service.generate_query_embedding()
              └─► OpenAI → query_embedding [float * 1536]
        └─► MemoryNodeDAO.recall(query, tags, limit, user_id, node_type)
              └─► find_similar(): SELECT ... ORDER BY embedding <=> query_embedding
              └─► get_by_tags(): tag-based candidates
              └─► resonance scoring: (semantic*0.6) + (tag*0.2) + (recency*0.2)
              └─► sorted results with resonance_score, tag_score, recency_score
```

**ARM analysis with memory recall + write (Phase 3)**
```
POST /arm/analyze
  └─► arm_router.py: Depends(get_current_user)
        └─► DeepSeekCodeAnalyzer.run_analysis(file_path, db, user_id)
              └─► [Step 2] chunk_content()
              └─► [Step 2b] bridge.recall_memories(query=filename, tags=["arm","analysis"], limit=3)
                    └─► MemoryNodeDAO.recall() → resonance-scored prior context
                    └─► inject as "Prior analysis memory" section in user_prompt
              └─► [Step 4] OpenAI GPT-4o analysis
              └─► [Step 6] INSERT INTO analysis_results [db.commit()]
              └─► [Step 6b] bridge.create_memory_node(node_type="outcome", tags=["arm","analysis",ext])
                    └─► MemoryNodeDAO.save() → embedding → INSERT INTO memory_nodes
                    (fire-and-forget)
```

**ARM code generation with memory write (Phase 3)**
```
POST /arm/generate
  └─► DeepSeekCodeAnalyzer.generate_code(prompt, language, db, user_id)
        └─► OpenAI GPT-4o generation
        └─► INSERT INTO code_generations [db.commit()]
        └─► bridge.create_memory_node(node_type="outcome", tags=["arm","codegen",language])
              └─► MemoryNodeDAO.save() → embedding → INSERT INTO memory_nodes
              (fire-and-forget)
```

**Genesis lock with memory write (Phase 3)**
```
POST /genesis/lock
  └─► genesis_router.py: Depends(get_current_user)
        └─► create_masterplan_from_genesis() → INSERT INTO master_plans [db.commit()]
        └─► bridge.create_memory_node(node_type="decision", tags=["genesis","masterplan","decision"])
              └─► MemoryNodeDAO.save() → embedding → INSERT INTO memory_nodes
              (fire-and-forget)
```

**Programmatic memory bridge (internal services — Phase 3)**
```
from bridge import create_memory_node, recall_memories

recall_memories(query, tags, limit, user_id, db)
  └─► MemoryNodeDAO.recall() → resonance scoring
  └─► returns [] on failure (never raises)

create_memory_node(content, source, tags, user_id, db, node_type)
  └─► MemoryNodeDAO.save() → embedding generation → INSERT INTO memory_nodes
  └─► returns transient MemoryNode if db=None (not persisted)
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
- `AINDY/server.js` gateway uses an in-memory user list and lacks persistence. ✅ **Gateway auth wired (Phase 3):** `X-API-Key` header is now sent on all FastAPI forwarding calls.
- Background tasks in `AINDY/main.py` are stubs and not using a formal scheduler/queue.
- `AINDY/services/memory_persistence.py` includes an orphan `save_memory_node(self, memory_node)` at module level (takes `self` but is not a class method; dead code that raises `TypeError` if called).
- ✅ **Resolved (2026-03-17)**: `AINDY/bridge/bridge.py` had a broken import path (`db.models.models` does not exist); fixed to `db.models.calculation`. Wrong-table architectural bug (`create_memory_node()` writes to `calculation_results` instead of `memory_nodes`) remains open — see `docs/roadmap/TECH_DEBT.md` §2.
- ✅ **Resolved (2026-03-17)**: `AINDY/routes/genesis_router.py` had three undefined name references (`call_genesis_synthesis_llm`, `create_masterplan_from_genesis`, `MasterPlan`) causing NameError crashes. All three imports added; `services/posture.py` stub created to resolve cascading ModuleNotFoundError.
- ✅ **Resolved (2026-03-17)**: `AINDY/tests/` comprehensive diagnostic suite added — 143 tests across 8 files (136 passing, 7 intentional `_WILL_FAIL` security gap tests). Coverage now spans services, memory bridge, Rust/C++ kernel, all route groups, models, and security.
- ✅ **Resolved (2026-03-17 Phase 2):** JWT authentication added to user-facing route groups: `task_router`, `leadgen_router`, `genesis_router`, `analytics_router`. `services/auth_service.py` provides `get_current_user` dependency (Bearer JWT), API key validation (`X-API-Key`), password hashing. Auth endpoints at `POST /auth/login`, `POST /auth/register`.
- ✅ **Resolved (2026-03-17 Phase 3):** All remaining unprotected routers secured. JWT (`get_current_user`): `seo_routes`, `authorship_router`, `arm_router`, `rippletrace_router`, `freelance_router`, `research_results_router`, `dashboard_router`, `social_router`. API key (`verify_api_key`): `db_verify_router`, `network_bridge_router`. Zero unprotected non-public routes remain.
- ✅ **Resolved (2026-03-17 Phase 3):** In-memory user store replaced with `db/models/user.py` (`users` table, UUID PK, unique email/username indexes). `auth_router.py` uses `register_user()` / `authenticate_user()` via `Depends(get_db)`. Migration: `37f972780d54_create_users_table`.
- C++ semantic kernel (`bridge/memory_bridge_rs/`) is built in debug mode only; `MemoryNode` has no vector embeddings, making semantic search inoperable. See `docs/roadmap/TECH_DEBT.md` §8.
- ✅ **Resolved (2026-03-17 ARM Phase 2):** Infinity Algorithm Thinking KPI System implemented. `services/arm_metrics_service.py` adds `ARMMetricsService` (5 metrics from DB history: Execution Speed, Decision Efficiency, AI Productivity Boost, Lost Potential, Learning Efficiency) and `ARMConfigSuggestionEngine` (advisory self-tuning suggestions, risk-classified, never auto-applied). New endpoints: `GET /arm/metrics` and `GET /arm/config/suggest`. Frontend: `ARMMetrics.jsx` and `ARMConfigSuggest.jsx`. ARM Phase 3 deferred: Memory Bridge feedback loop (bridge design in progress); auto-approve low-risk suggestions.
- ✅ **Resolved (2026-03-17 Genesis Blocks 1-3):** Genesis/MasterPlan module fully implemented end-to-end. Migration `a1b2c3d4e5f6` adds `synthesis_ready`, `draft_json`, `locked_at`, `user_id_str` to `genesis_sessions`; `user_id`, `status` to `master_plans`. All Genesis routes user-scoped. `call_genesis_synthesis_llm()` real GPT-4o call (replaces stub). `determine_posture()` real logic (Stable/Accelerated/Aggressive/Reduced). New router `masterplan_router.py` (prefix `/masterplans`, 4 JWT-auth endpoints). `GET /genesis/session/{id}` and `GET /genesis/draft/{id}` added. `POST /genesis/synthesize` gated on `synthesis_ready`. Frontend: Genesis.jsx auth-wired, synthesis-ready banner, draft preview, lock confirmation; GenesisDraftPreview.jsx new; MasterPlanDashboard.jsx rewritten with authenticated `listMasterPlans()` and correct status badges.

Full inventory: `docs/roadmap/TECH_DEBT.md`.

## Notes for AI Agents
- Prefer edits in `AINDY/services/` for domain logic and `AINDY/routes/` for HTTP contracts.
- Avoid introducing new cross-module state. Use dependency injection (FastAPI `Depends`) and per-request sessions.
- Keep symbolic memory files (`AINDY/memoryevents/`, `AINDY/memorytraces/`) unchanged unless explicitly asked.

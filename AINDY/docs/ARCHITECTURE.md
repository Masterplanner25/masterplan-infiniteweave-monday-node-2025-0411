# A.I.N.D.Y. System Architecture

**Last updated:** 2026-03-17
**Branch:** feature/cpp-semantic-engine
**Version:** 1.0.0 (Social Layer) + unreleased C++ Semantic Engine

---

## Stack Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  (React/Vite)                                     │
│  ProfileView · Feed · PostComposer · TaskDashboard          │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP / REST
┌───────────────────────▼─────────────────────────────────────┐
│  FastAPI Application  (main.py)                             │
│  18 routers · startup background tasks · CORS middleware    │
│  NO authentication middleware (see TECH_DEBT.md — Critical) │
└──────┬────────────────┬────────────────┬────────────────────┘
       │                │                │
┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────────────────┐
│  Services   │  │   Routes    │  │  Bridge Layer           │
│  layer      │  │  (prefix)   │  │  bridge_router.py       │
│  (pure      │  │  /tasks     │  │  (/bridge/*)            │
│  business   │  │  /social    │  │  HMAC permission model  │
│  logic)     │  │  /analytics │  │  → MemoryNodeDAO        │
│             │  │  /bridge    │  │  → memory_nodes table   │
│  C++ kernel │  │  /research  │  └────────────────────────┘
│  (via Rust  │  │  /leadgen   │
│  PyO3)      │  │  /freelance │
└──────┬──────┘  │  … 13 more  │
       │         └──────┬──────┘
┌──────▼─────────────────▼──────────────────────────────────┐
│  Data Layer                                                │
│  PostgreSQL (SQLAlchemy)         MongoDB (motor/pymongo)   │
│  ├── tasks                       └── social posts          │
│  ├── memory_nodes (UUID/JSONB)       profiles              │
│  ├── calculation_results             trust tiers           │
│  ├── research_results                                      │
│  ├── social_profiles                                       │
│  ├── leadgen / freelance                                   │
│  └── system_health_log                                     │
└────────────────────────────────────────────────────────────┘
       │
┌──────▼────────────────────────────────────────────────────┐
│  C++ Semantic Kernel  (memory_bridge_rs PyO3 extension)   │
│  Python → Rust (PyO3) → C++ (extern "C" FFI)             │
│  cosine_similarity · weighted_dot_product                 │
│  Build: cc crate + MSVC VS 2022 x64                       │
└───────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
AINDY/
├── main.py                     # FastAPI app, router registration, startup tasks
├── requirements.txt
├── version.json                # ⚠ stale — reports 0.9.0-pre, should be 1.0.0
├── system_manifest.json        # ⚠ stale — same version issue
│
├── bridge/                     # Memory Bridge + C++ kernel
│   ├── bridge.py               # Solon Protocol: create_memory_node(), trace ops
│   │                           # ⚠ create_memory_node() writes wrong table (TECH_DEBT)
│   ├── trace_permission.py     # ⚠ unconnected — not imported anywhere
│   ├── smoke_memory.py         # ⚠ broken imports — won't run as-is
│   ├── Bridgeimport.py         # ⚠ loose test — runs on import, no pytest guard
│   ├── benchmark_similarity.py # C++ vs Python benchmark (dim=1536)
│   ├── memory_bridge_rs/       # Rust/PyO3 extension crate
│   │   ├── src/lib.rs          # MemoryNode, MemoryTrace, semantic_similarity, weighted_dot_product
│   │   ├── src/cpp_bridge.rs   # extern "C" FFI wrappers
│   │   ├── build.rs            # cc-crate build: compiles semantic.cpp
│   │   ├── Cargo.toml          # pyo3 = "0.19", cc = "1" (build-dep)
│   │   └── memory_cpp/
│   │       ├── semantic.h      # extern "C" header
│   │       └── semantic.cpp    # cosine_similarity, weighted_dot_product
│   └── archive/                # superseded files — do not compile
│       ├── memory_bridge_core_draft.rs
│       └── Memorybridgerecognitiontrace.rs
│
├── routes/                     # FastAPI routers
│   ├── __init__.py             # ROUTERS list — all 18 routers registered here
│   ├── bridge_router.py        # /bridge/* — MemoryNodeDAO, HMAC TracePermission
│   ├── task_router.py          # /tasks
│   ├── social_router.py        # /social — profiles, feed, trust tiers
│   ├── analytics_router.py     # /analytics
│   ├── research_results_router.py
│   ├── leadgen_router.py
│   ├── freelance_router.py
│   ├── rippletrace_router.py
│   ├── authorship_router.py
│   ├── seo_routes.py
│   ├── health_router.py
│   ├── health_dashboard_router.py
│   ├── dashboard_router.py
│   ├── network_bridge_router.py
│   ├── db_verify_router.py
│   ├── arm_router.py
│   ├── genesis_router.py
│   └── main_router.py
│
├── services/                   # Business logic
│   ├── calculation_services.py # Infinity Algorithm formulas + C++ kernel integration
│   ├── task_services.py        # Task CRUD + real-time profile update trigger
│   ├── memory_persistence.py   # MemoryNodeDAO → memory_nodes table (correct path)
│   ├── research_results_service.py
│   ├── leadgen_service.py      # calls bridge.create_memory_node() — affected by wrong-table bug
│   ├── freelance_service.py
│   ├── deepseek_arm_service.py
│   ├── genesis_ai.py
│   ├── authorship_services.py
│   ├── rippletrace_services.py
│   ├── network_bridge_services.py
│   ├── projection_service.py
│   ├── masterplan_factory.py
│   ├── seo_services.py
│   ├── youtube_service.py
│   └── analytics/
│       ├── linkedin_adapter.py
│       └── rate_calculator.py
│
├── db/                         # Database layer
│   ├── database.py             # SQLAlchemy engine + session factory
│   ├── mongo_setup.py          # MongoDB connection (motor)
│   ├── create_all.py           # Table creation script
│   └── models/
│       ├── __init__.py         # Re-exports all models (Base, CalculationResult, …)
│       ├── task.py             # Task model
│       ├── calculation.py      # CalculationResult — misused by create_memory_node()
│       ├── metrics_models.py
│       ├── social_models.py    # SocialProfile, SocialPost, TrustTier
│       ├── research_results.py
│       ├── leadgen_model.py
│       ├── freelance.py
│       ├── author_model.py
│       ├── arm_models.py
│       ├── masterplan.py
│       └── system_health_log.py
│
├── schemas/                    # Pydantic request/response schemas
│   └── analytics_inputs.py     # TaskInput, EngagementInput, … (13 schemas)
│
├── docs/
│   ├── ARCHITECTURE.md         # ← this file
│   └── TECH_DEBT.md            # Known debt, risks, deferred work
│
├── tests/                      # Integration / performance tests
├── memoryevents/               # Symbolic recognition events (narrative)
├── memorytraces/               # Contextual records (narrative)
└── tools/                      # Meta-systems (Authorship, Epistemic Reclaimer)
```

---

## Data Flow

### Task → Velocity → Profile loop (v1.0 Social Layer)

```
POST /tasks/complete
  └─► task_services.py: mark_task_complete()
        └─► update SocialProfile velocity + TWR score (PostgreSQL)
              └─► bridge.py: create_memory_node()  ← ⚠ writes CalculationResult, NOT memory_nodes
```

### Memory Node creation (correct path)

```
POST /bridge/nodes  (bridge_router.py)
  └─► TracePermission.verify_hmac()
        └─► MemoryNodeDAO.create()  (memory_persistence.py)
              └─► INSERT INTO memory_nodes (UUID, content, tags, node_type, extra)
```

### Engagement Score (C++ kernel path)

```
POST /analytics/engagement
  └─► calculate_engagement_score() (calculation_services.py)
        └─► _cpp_weighted_dot([likes, shares, comments, clicks, time_on_page],
                               [2.0, 3.0, 1.5, 1.0, 0.5])
              └─► Rust: weighted_dot_product() (lib.rs)
                    └─► C++: weighted_dot_product() (semantic.cpp)
```

---

## Known Architectural Gaps

| Gap | Severity | Location | Detail |
|-----|----------|----------|--------|
| No authentication | 🔴 Critical | All routes | No token/API-key middleware; HMAC only on `/bridge/nodes` |
| Wrong table in create_memory_node() | 🔴 Critical | `bridge/bridge.py` | Writes `CalculationResult`, discards content/tags |
| C++ build in debug only | 🟡 High | `memory_bridge_rs/` | AppControl blocks `target/release/`; FFI overhead > Python in debug |
| No vector embeddings on MemoryNode | 🟡 High | `memory_bridge_rs/src/lib.rs` | C++ cosine kernel has no data to operate on |
| smoke_memory.py broken imports | 🟡 High | `bridge/smoke_memory.py` | `from base import Base` fails; needs project-relative paths |
| stale version.json / system_manifest.json | 🟡 High | root | Reports `0.9.0-pre`; current is `1.0.0` |
| trace_permission.py unconnected | 🟢 Low | `bridge/trace_permission.py` | Not imported anywhere |
| Bridgeimport.py runs on import | 🟢 Low | `bridge/Bridgeimport.py` | No `__main__` guard, no pytest structure |

Full details: `docs/TECH_DEBT.md`

---

## Build & Run

### Backend

```bash
cd AINDY
python -m venv venv
venv/Scripts/activate           # Windows
pip install -r requirements.txt

# Optional: build C++ kernel (requires Rust toolchain + MSVC)
cd bridge/memory_bridge_rs
maturin develop                 # debug build
cd ../..

# Database
python db/create_all.py         # or: alembic upgrade head

# Server
uvicorn main:app --reload
# → http://127.0.0.1:8000
```

### Frontend

```bash
cd client   # or wherever the React/Vite root is
npm install
npm run dev
```

### Requirements

- Python 3.10+
- PostgreSQL (connection string via `DATABASE_URL` env var)
- MongoDB (connection string via `MONGO_URL` env var — required for Social Layer)
- Rust + maturin 1.12+ (optional — for C++ kernel)
- MSVC VS 2022 x64 (optional — for C++ compilation on Windows)

# A.I.N.D.Y. Technical Debt Register

This document tracks known technical debt, deferred work,
and items requiring follow-up. Updated with each significant
change.

**Last updated:** 2026-03-17
**Branch:** feature/cpp-semantic-engine

---

## Open Items

### 🔴 Critical

#### No authentication on any FastAPI endpoint
Every route in the application is fully public. There is no
token validation, API key check, or session middleware. The
only exception is `bridge_router.py`, which uses an HMAC
signature on the `permission` field of node creation/link
requests — but the secret defaults to `"dev-secret-must-change"`.

**Risk:** Any caller can read or write tasks, memory nodes,
research results, social profiles, and analytics data.

**Fix:** Add OAuth2 Bearer token middleware at the FastAPI
app level, or at minimum add an API key header check.

**Files:**
- `main.py` (add middleware)
- `routes/*.py` (add `Depends(verify_token)` to write endpoints)

**Added:** 2026-03-17

---

#### `create_memory_node()` writes to the wrong table
`bridge/bridge.py::create_memory_node()` persists to the
`calculation_results` table via `CalculationResult`, storing
only the node `title` as `metric_name` and `0.0` as
`result_value`. The actual `content` and `tags` are silently
discarded. The dedicated `memory_nodes` table (with proper
UUID, content, tags, node_type, extra columns) exists in the
database but is never populated by this path.

Meanwhile, `bridge_router.py` correctly uses `MemoryNodeDAO`
to write to `memory_nodes`. Two consumers of "create memory
node" use different tables, producing split state.

**Risk:** All memory nodes created via `leadgen_service.py`
(and any other service that calls `create_memory_node()`)
are silently lost — they produce a row in `calculation_results`
that looks like a metric, not a memory node.

**Fix:** Rewrite `bridge.py::create_memory_node()` to use
`MemoryNodeDAO` and write to the `memory_nodes` table.

**Files:**
- `bridge/bridge.py` (fix `create_memory_node()`)
- `services/leadgen_service.py` (will auto-fix once bridge is fixed)

**Added:** 2026-03-17

---

### 🟡 High Priority

#### Verify C++ kernel release build performance
The C++ semantic similarity and `weighted_dot_product` kernels
were built in debug mode due to Windows Application Control
(AppControl) policy blocking writes to `target/release/` and
`target/debug/` directories for new build scripts.

Debug benchmark (dim=1536, 10k iterations):
- Pure Python: 2.753s (0.2753 ms/call)
- C++ debug:   3.844s (0.3844 ms/call)
- Status: C++ SLOWER in debug due to FFI overhead

Expected release build result: 10–50x improvement over Python
for high-dimensional vector operations.

**Action required:**
1. Run `maturin develop --release` in an environment where
   AppControl does not block `target/release/` writes
   (deployment server, CI, or AppControl policy exception)
2. Re-run `bridge/benchmark_similarity.py` and record results
3. Update this item with actual speedup numbers
4. If release speedup is < 3x, evaluate whether the C++ layer
   complexity is justified vs numpy/scipy alternatives

**Files:**
- `bridge/benchmark_similarity.py`
- `bridge/memory_bridge_rs/Cargo.toml`

**Added:** 2026-03-17
**Target:** Before embedding MemoryNode vectors (next milestone)

---

#### Add vector embeddings to MemoryNode for semantic search
The C++ `cosine_similarity` kernel is implemented and wired
but has no data to operate on. `MemoryNode` currently stores
text content only — no vector embeddings anywhere in the schema.

To activate semantic memory search:
1. Add `embedding: Vec<f64>` field to `MemoryNode` in `lib.rs`
2. Generate embeddings via OpenAI `text-embedding-ada-002`
   (dim=1536) when a `MemoryNode` is created
3. Store embeddings in PostgreSQL (pgvector extension) or as
   a serialized JSONB column
4. Wire `cosine_similarity()` to `MemoryNode.compare(other)`
5. Add a semantic search endpoint to `bridge_router.py`

The C++ kernel was built anticipating this feature.

**Files:**
- `bridge/memory_bridge_rs/src/lib.rs` (add embedding field)
- `bridge/bridge.py` (update Python `MemoryNode`)
- `services/` (new embedding generation service)
- `routes/bridge_router.py` (new `/bridge/nodes/search/semantic` endpoint)

**Added:** 2026-03-17
**Target:** Next sprint

---

#### `smoke_memory.py` has broken imports
`bridge/smoke_memory.py` sets `PROJECT_ROOT` to its own
directory (`bridge/`) and then does:
```python
from base import Base                            # broken
from memory_persistence import MemoryNodeDAO    # broken
```
The correct imports are `from db.database import Base` and
`from services.memory_persistence import MemoryNodeDAO`.
Running this script as-is will always fail with `ModuleNotFoundError`.

**Fix:** Update imports to use project-relative paths, or add
a proper `sys.path` setup using the AINDY root.

**Files:**
- `bridge/smoke_memory.py`

**Added:** 2026-03-17

---

#### `version.json` and `system_manifest.json` are stale
Both files report version `0.9.0-pre` but `CHANGELOG.md`
has `v1.0` (Social Layer) as the current release. These
files are not updated automatically.

**Fix:** Update `version` field to `1.0.0` in both files
and update `branch`, `merged_from`, and `status` fields.

**Files:**
- `AINDY/version.json`
- `AINDY/system_manifest.json`

**Added:** 2026-03-17

---

### 🟢 Low Priority / Nice to Have

#### `trace_permission.py` is unconnected
`bridge/trace_permission.py` defines a `trace_permission()`
function but is not imported by anything in the codebase.
It is not exported from `bridge/__init__.py` and not used
in any service or route.

**Options:**
- Export it from `bridge/__init__.py` and use it in
  `bridge_router.py` as the permission logging layer
- Or delete it if the HMAC-based `TracePermission` in
  `bridge_router.py` supersedes it

**Files:**
- `bridge/trace_permission.py`
- `bridge/__init__.py`

**Added:** 2026-03-17

---

#### `Bridgeimport.py` is a loose test script
`bridge/Bridgeimport.py` is a 12-line manual test script
that imports from `memory_bridge_rs`. It is not a test
module (no pytest), not imported anywhere, and has no
`__name__ == "__main__"` guard. It runs immediately on
import.

**Fix:** Either move to `tests/` as a proper pytest test,
or add the `if __name__ == "__main__":` guard.

**Files:**
- `bridge/Bridgeimport.py`

**Added:** 2026-03-17

---

#### Orphan `save_memory_node()` at module level in `memory_persistence.py`
`services/memory_persistence.py` defines a standalone function
`save_memory_node(self, memory_node)` at module level (lines 16–23),
outside the `MemoryNodeDAO` class. It takes `self` as a parameter —
meaning it would raise `TypeError` if called. It also calls
`prepare_input_text` but builds a `MemoryNodeModel` without persisting
it (no `db.add()` / `db.commit()`).

**Risk:** The function is dead code. Any caller that reaches it will
get a `TypeError`. It creates the illusion of a second persistence
path that does nothing.

**Fix:** Either delete the function entirely (the `MemoryNodeDAO`
class below it already handles all persistence) or complete it by
converting it to a proper standalone function that accepts a `db`
session.

**Files:**
- `services/memory_persistence.py` (lines 16–23)

**Added:** 2026-03-17

---

#### `/bridge/user_event` only logs to stdout — no persistence
`routes/bridge_router.py::bridge_user_event()` accepts user join events
via `POST /bridge/user_event` and responds with `{"status": "logged", …}`,
but only calls `print()`. No write to any database table, no RippleTrace
emission, no file log.

**Risk:** User join events are silently lost on process restart.
The response `{"status": "logged"}` implies persistence that does not exist.

**Fix:** Either persist to a dedicated `user_events` table, emit a
RippleTrace event (as `create_node` does), or rename the response field
to `{"status": "received"}` to set accurate expectations.

**Files:**
- `routes/bridge_router.py` (lines 159–164)

**Added:** 2026-03-17

---

#### Remove `bridge/archive/` folder after team review
Two files were archived rather than deleted:
- `bridge/archive/memory_bridge_core_draft.rs` (old Rust draft)
- `bridge/archive/Memorybridgerecognitiontrace.rs` (commemorative)

These can be permanently deleted once the team confirms
nothing useful was lost.

**Added:** 2026-03-17

---

## Closed Items

#### ~~`AINDY_README.md` architecture tree references archived files~~
Fixed 2026-03-17 — architecture tree updated to reflect current
`bridge/` structure (removed `memorycore.py`, `memlibrary.py`,
`Memorybridgerecognitiontrace.py`; added `memory_bridge_rs/` subtree).
New sections "Memory Bridge / C++ Semantic Engine" and
"The Infinity Algorithm" added.

**Closed:** 2026-03-17

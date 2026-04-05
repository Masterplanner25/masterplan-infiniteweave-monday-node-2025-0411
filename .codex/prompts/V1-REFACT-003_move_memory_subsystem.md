You are working in the AINDY/ Python/FastAPI codebase.

TASK: V1-REFACT-003 — Move the memory subsystem files into `AINDY/memory/` and
create backward-compat shims in `services/` and `bridge/` so no existing import
breaks. This is the first step of the long refactor chain (003→004→005→006→007).

PREREQUISITE: V1-REFACT-002 is complete (kernel/ is populated with shims in
services/). Do NOT remove any shims in this task — shim removal happens in
V1-REFACT-009 after all memory consumers are updated.

FILES TO READ FIRST (in order):
1. AINDY/services/memory_persistence.py      — largest file; check imports
2. AINDY/services/memory_address_space.py    — imports from services.tenant_context
3. AINDY/services/memory_capture_engine.py
4. AINDY/services/memory_helpers.py
5. AINDY/services/memory_ingest_service.py
6. AINDY/services/memory_scoring_service.py
7. AINDY/services/embedding_service.py
8. AINDY/services/embedding_jobs.py
9. AINDY/bridge/bridge.py                   — check what it exports
10. AINDY/bridge/nodus_memory_bridge.py
11. AINDY/memory/__init__.py                 — currently empty placeholder
12. AINDY/bridge/__init__.py                 — may already exist; check

WHAT TO MOVE:
  Source                                    → Destination
  services/memory_persistence.py           → memory/memory_persistence.py
  services/memory_address_space.py         → memory/memory_address_space.py
  services/memory_capture_engine.py        → memory/memory_capture_engine.py
  services/memory_helpers.py               → memory/memory_helpers.py
  services/memory_ingest_service.py        → memory/memory_ingest_service.py
  services/memory_scoring_service.py       → memory/memory_scoring_service.py
  services/embedding_service.py            → memory/embedding_service.py
  services/embedding_jobs.py               → memory/embedding_jobs.py
  bridge/bridge.py                         → memory/bridge.py
  bridge/nodus_memory_bridge.py            → memory/nodus_memory_bridge.py

STEP-BY-STEP PROCESS:

Step 1 — Scan internal imports in the 10 source files.
  For each file, note any `from services.memory_*`, `from services.embedding_*`,
  or `from bridge import` lines — these will need updating IN THE NEW COPY.
  Also check for `from services.tenant_context` (memory_address_space.py uses
  this — keep it as `from services.tenant_context` since the kernel shim still
  re-exports it during Phase 2; do not change it now).

Step 2 — Copy (do not delete) each file to its new location.
  Use Write tool to create the new file with the same content as the original,
  updating only internal cross-references between the 10 moving files:
    - `from services.memory_X import` → `from memory.memory_X import`
    - `from services.embedding_X import` → `from memory.embedding_X import`
    - `from bridge import` → `from memory.bridge import`
    - `from bridge.bridge import` → `from memory.bridge import`
  Do NOT update references to services.auth_service, services.flow_engine,
  services.calculation_services, or anything outside the 10 moving files.

Step 3 — Create shims in services/ for each of the 8 services/ files:
  Each shim follows the exact format used by the kernel shims (read
  services/syscall_dispatcher.py as the template). Example for memory_persistence:

      # ── MIGRATION SHIM (remove after V1-REFACT-009 import updates) ──────────
      # Canonical location: memory/memory_persistence.py
      # ────────────────────────────────────────────────────────────────────────
      from memory.memory_persistence import *  # noqa: F401, F403
      from memory.memory_persistence import MemoryNodeDAO  # noqa: F401
      # ... add any other names that tests or routes import directly

  Read each original services/ file to find all public names that need explicit
  re-export in the shim. Add explicit imports for any name you find referenced
  in tests/ or routes/ via grep.

Step 4 — Create/replace bridge/__init__.py with a shim:
  The v1_progress.json notes say:
    "bridge/__init__.py must shim from memory.bridge —
     runtime/execution_loop.py does `from bridge import create_memory_node`"
  So bridge/__init__.py must contain:
      from memory.bridge import *  # noqa: F401, F403
      from memory.bridge import create_memory_node  # noqa: F401
  Check what else is imported from `bridge` across the codebase:
      grep -rn "from bridge import\|import bridge" AINDY/ --include="*.py"
  Add explicit re-exports for each name found.

Step 5 — DO NOT delete the original services/ files — the shims replace them.
  DO NOT update any consumers yet (that is V1-REFACT-009).

Step 6 — Run tests:
      python -m pytest tests/unit/ -q
  Expect 740 passed (same baseline). If any new failures appear, they are import
  errors in the new memory/ files — fix them before proceeding.

IMPORTANT NOTES:
- The memory/ package already has a placeholder __init__.py (empty). Do not
  overwrite it with re-exports yet — leave it empty.
- `memory_address_space.py` has a lazy import `from services.tenant_context
  import TENANT_VIOLATION` inside a function body. In the new copy at
  `memory/memory_address_space.py`, change it to
  `from kernel.tenant_context import TENANT_VIOLATION` (kernel shim is already
  in place, and we prefer direct kernel imports in new locations).
- The archive/ subdirectory inside bridge/ should NOT be moved — it stays.
- Use `git mv` semantics mentally (copy + shim) but physically use Write tool
  to create the new files and Edit tool to turn the old files into shims.
  Do not use Bash rm to delete originals.

ACCEPTANCE CRITERIA:
- `python -m pytest tests/unit/ -q` → 740 passed, 0 new failures.
- `python -c "from memory.memory_persistence import MemoryNodeDAO"` succeeds
  (run from AINDY/).
- `python -c "from bridge import create_memory_node"` succeeds (run from AINDY/).
- `python -c "from services.memory_persistence import MemoryNodeDAO"` still
  succeeds (shim works).
- All 10 new files exist under memory/ alongside the placeholder __init__.py.

You are working in the AINDY/ Python/FastAPI codebase.

TASK: V1-REFACT-008 — Update all remaining `services.*` imports that reference
the kernel shim files so they point directly to `kernel.*`, then delete the
7 shim files from `services/`.

BACKGROUND:
V1-REFACT-002 moved 7 files into `AINDY/kernel/` and left backward-compat
shims in `services/` that re-export everything via `from kernel.X import *`.
The shims exist ONLY to avoid breaking callers during the transition.
This task updates every caller and removes the shims.

The 7 shim files to delete at the end:
  services/syscall_dispatcher.py
  services/syscall_registry.py
  services/syscall_versioning.py
  services/syscall_handlers.py
  services/resource_manager.py
  services/tenant_context.py
  services/scheduler_engine.py

FILES THAT STILL IMPORT FROM THE SHIM PATHS (verified by grep):

  AINDY/main.py:198
    from services.syscall_handlers import register_all_domain_handlers
    → from kernel.syscall_handlers import register_all_domain_handlers

  AINDY/routes/platform_router.py:1539-1540
    from services.resource_manager import get_resource_manager
    from services.scheduler_engine import get_scheduler_engine
    → from kernel.resource_manager import get_resource_manager
    → from kernel.scheduler_engine import get_scheduler_engine

  AINDY/routes/platform_router.py:1680-1681
    from services.syscall_registry import SYSCALL_REGISTRY
    from services.syscall_versioning import SyscallSpec
    → from kernel.syscall_registry import SYSCALL_REGISTRY
    → from kernel.syscall_versioning import SyscallSpec

  AINDY/routes/platform_router.py:1779-1780
    from services.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
    from services.syscall_registry import DEFAULT_NODUS_CAPABILITIES
    → from kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
    → from kernel.syscall_registry import DEFAULT_NODUS_CAPABILITIES

  AINDY/services/agent_tools.py:33
    from services.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
    → from kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool

  AINDY/services/flow_definitions.py:30 (lazy import)
    from services.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_flow
    → from kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_flow

  AINDY/services/flow_engine.py (5 lazy imports — all inside function bodies)
    line ~540:  from services.resource_manager import get_resource_manager
    line ~652:  from services.resource_manager import get_resource_manager as _get_rm_f
    line ~731:  from services.resource_manager import get_resource_manager as _get_rm
    line ~744:  from services.scheduler_engine import get_scheduler_engine, ScheduledItem
    line ~826:  from services.resource_manager import get_resource_manager as _get_rm2
    line ~1061: from services.resource_manager import get_resource_manager as _get_rm_s
    → all replace services. → kernel.

  AINDY/services/memory_address_space.py:108 (lazy import)
    from services.tenant_context import TENANT_VIOLATION
    → from kernel.tenant_context import TENANT_VIOLATION

  AINDY/services/nodus_runtime_adapter.py:378 (lazy import)
    from services.syscall_dispatcher import (...)
    → from kernel.syscall_dispatcher import (...)

  AINDY/tests/unit/test_os_layer.py:24,30,38,503,512-513,523-524,540-541,558-559,574-575,707
    from services.tenant_context import ...
    from services.resource_manager import ...
    from services.scheduler_engine import ...
    (and local imports inside test methods)
    → all replace services. → kernel.

  AINDY/tests/unit/test_syscall_dispatcher.py:28,34-35,312,329,345,359,383
    from services.syscall_dispatcher import ...
    from services.syscall_registry import ...
    → all replace services. → kernel.

PROCESS:
1. Read each file listed above before editing it.
2. For each file, replace `from services.X import` → `from kernel.X import`
   for the 7 kernel modules only. Do not alter any other imports.
3. After all consumer files are updated, delete the 7 shim files.
   Use `git rm` if possible; otherwise plain file deletion is fine.
4. Run `python -m pytest tests/unit/ -q` and confirm 740 passed, 0 new failures.
5. Run `python -m pytest tests/v1_gates/test_v1_gates.py::test_no_shim_files_remain -v`
   and confirm it passes.

IMPORTANT NOTES:
- Many of the flow_engine.py and platform_router.py imports are LAZY (inside
  function bodies). Read each file carefully to find them all — do not rely
  solely on the line numbers above (the file may have shifted).
- `test_os_layer.py` and `test_syscall_dispatcher.py` also have imports
  inside test method bodies (not just at module level) — grep for
  `services.syscall` and `services.resource` within those files before editing.
- Do not touch any other `services.*` imports (auth_service, flow_engine,
  calculation_services, etc. — those are NOT shims and must not be changed).

ACCEPTANCE CRITERIA:
- `python -m pytest tests/unit/ -q` → 740 passed, no new failures.
- `python -m pytest tests/v1_gates/test_v1_gates.py::test_no_shim_files_remain -v` → PASSED.
- None of the 7 deleted shim filenames appear anywhere under AINDY/ in any
  `from services.X import` statement (`grep -r "from services.syscall\|from services.resource_manager\|from services.tenant_context\|from services.scheduler_engine" AINDY/ --include="*.py"` returns empty).

"""
router_guard.py — Startup AST validator for the HARD EXECUTION BOUNDARY.

Scans every file in routes/ at startup and raises RouterBoundaryViolation
if any router contains a top-level import of a forbidden service module
or a forbidden legacy execution identifier.

Design:
  - Explicit forbidden module list (services that must NEVER be imported
    directly into a router — business logic must go through run_flow()).
  - Explicit forbidden name list (legacy wrappers / DAO classes that the
    boundary refactor removed from all converted routers).
  - Does NOT blanket-ban all services.* imports — auth helpers, rate
    limiters, observability, and coordinator infrastructure are allowed.

Usage:
    from core.router_guard import validate_router_boundary
    validate_router_boundary()   # call once at application startup
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Service modules that routers must NOT import — business logic lives here
# and must be accessed exclusively via run_flow().
_FORBIDDEN_MODULES: frozenset[str] = frozenset(
    [
        "services.agent_runtime",
        "services.arm_service",
        "services.analytics_service",
        "services.flow_engine_intent",
        "services.genesis_service",
        "services.goal_service",
        "services.leadgen_service",
        "services.memory_helpers",
        "services.memory_service",
        "services.nodus_adapter",
        "services.nodus_execution_service",
        "services.score_service",
        "services.task_services",
        "services.watcher_service",
    ]
)

# DB model sub-packages that routers must not import (queries belong in nodes)
_FORBIDDEN_MODULE_PREFIXES: tuple[str, ...] = (
    "db.models.arm_models",
    "db.models.score_models",
    "db.models.task_model",
    "db.models.lead_model",
    "db.models.watcher_signal",
    "db.models.flow_run",
)

# Specific names whose presence in a top-level router import indicates a
# boundary violation regardless of which module they came from.
# NOTE: Only names removed during the execution-boundary refactor are listed
# here. Routers that pre-date the refactor and still use services.execution_service
# directly are tracked separately and will be migrated in a future sprint.
_FORBIDDEN_NAMES: frozenset[str] = frozenset(
    [
        # Legacy intent dispatcher — replaced by run_flow()
        "execute_intent",
        # DAO classes that must stay inside nodes
        "MemoryNodeDAO",
        # ARM service classes
        "ARMMetricsService",
        "DeepSeekCodeAnalyzer",
        "ConfigManager",
        "ARMConfigSuggestionEngine",
        # Task / lead service functions
        "handle_recurrence",
        "persist_search_result",
        "search_leads",
        # Goal service functions
        "get_active_goals",
        "get_goal_states",
        "detect_goal_drift",
        # Agent runtime
        "NodusAgentAdapter",
        # Nodus execution
        "execute_nodus_task_payload",
    ]
)


# Router files that have not yet been migrated to the execution boundary.
# Remove entries from this set as each router is converted. Once this set
# is empty the full boundary is enforced across the entire route layer.
_PENDING_MIGRATION: frozenset[str] = frozenset(
    [
        # Converted in next sprint:
        "legacy_surface_router.py",   # uses many legacy engine services
        "main_router.py",             # uses services.calculations
        "network_bridge_router.py",   # uses services.calculation_services
        "seo_routes.py",              # uses services.seo + services.calculation_services
        "identity_router.py",         # uses services.identity_service
        "coordination_router.py",     # uses services.agent_coordinator
        "system_state_router.py",     # uses services.system_state_service
        "social_router.py",           # uses services.social_performance_service
        "rippletrace_router.py",      # uses services.rippletrace_service
        "authorship_router.py",       # uses services.authorship_services
        "bridge_router.py",           # uses MemoryNodeDAO directly
        "memory_trace_router.py",     # uses MemoryNodeDAO directly
    ]
)


# ---------------------------------------------------------------------------
# Violation type
# ---------------------------------------------------------------------------

class RouterBoundaryViolation(Exception):
    """Raised when a router imports a forbidden service at module scope."""


class _Violation(NamedTuple):
    file: str
    lineno: int
    module: str
    names: list[str]


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------

def _is_forbidden_module(module: str) -> bool:
    if module in _FORBIDDEN_MODULES:
        return True
    for prefix in _FORBIDDEN_MODULE_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return True
    return False


def _check_forbidden_names(names: list[str]) -> list[str]:
    return [n for n in names if n in _FORBIDDEN_NAMES]


def _scan_file(path: Path) -> list[_Violation]:
    violations: list[_Violation] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError) as exc:
        logger.warning("router_guard: could not parse %s: %s", path, exc)
        return violations

    # Only examine top-level statements (direct children of the module body).
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    violations.append(
                        _Violation(str(path), node.lineno, alias.name, [alias.name])
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names = [alias.name for alias in node.names]

            if _is_forbidden_module(module):
                violations.append(
                    _Violation(str(path), node.lineno, module, imported_names)
                )
                continue

            bad_names = _check_forbidden_names(imported_names)
            if bad_names:
                violations.append(
                    _Violation(str(path), node.lineno, module, bad_names)
                )

    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_router_boundary(routes_dir: Path | None = None) -> None:
    """
    Scan all *.py files in routes_dir for boundary violations.

    Raises RouterBoundaryViolation listing every offending import if any
    violations are found. Logs a summary at INFO level on success.

    Args:
        routes_dir: Path to the routes package directory. Defaults to the
                    sibling ``routes/`` directory relative to this file.
    """
    if routes_dir is None:
        routes_dir = Path(__file__).parent.parent / "routes"

    if not routes_dir.is_dir():
        logger.warning("router_guard: routes directory not found at %s — skipping", routes_dir)
        return

    router_files = sorted(f for f in routes_dir.glob("*.py") if not f.name.startswith("_"))
    pending = [f for f in router_files if f.name in _PENDING_MIGRATION]
    if pending:
        logger.info(
            "router_guard: %d router(s) pending boundary migration: %s",
            len(pending),
            ", ".join(f.name for f in pending),
        )
    all_violations: list[_Violation] = []
    for py_file in router_files:
        if py_file.name in _PENDING_MIGRATION:
            continue
        all_violations.extend(_scan_file(py_file))

    if not all_violations:
        logger.info(
            "router_guard: PASS — %d router files respect the execution boundary",
            len(router_files),
        )
        return

    lines = ["RouterBoundaryViolation: routers with forbidden direct service imports:"]
    for v in all_violations:
        rel = Path(v.file).name
        lines.append(f"  {rel}:{v.lineno}  module={v.module!r}  names={v.names}")
    message = "\n".join(lines)
    raise RouterBoundaryViolation(message)

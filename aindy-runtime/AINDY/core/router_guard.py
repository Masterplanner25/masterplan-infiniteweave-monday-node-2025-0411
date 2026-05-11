"""Generic router boundary guard.

The platform router guard enforces structural rules that keep routers from
reaching directly into app/service implementation modules. App-specific route
policy belongs in app-owned guards registered through the platform registry.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, NamedTuple

from AINDY.platform_layer.registry import get_route_guard

logger = logging.getLogger(__name__)


class RouterBoundaryViolation(Exception):
    """Raised when a router violates the generic routing boundary."""


class _Violation(NamedTuple):
    file: str
    lineno: int
    module: str
    names: list[str]
    is_deferred: bool = False


def _normalise_module(module: str) -> str:
    return module.removeprefix("AINDY.")


def _is_forbidden_module(module: str) -> bool:
    normalised = _normalise_module(module)
    parts = tuple(part for part in normalised.split(".") if part)

    if len(parts) >= 3 and parts[0] == "apps" and parts[2] == "services":
        return True
    if len(parts) >= 3 and parts[0] == "apps" and parts[2] == "models":
        return True
    return False


def _app_route_domain(path: Path) -> str | None:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "apps" and index + 2 < len(parts) and parts[index + 2] == "routes":
            return parts[index + 1]
    return None


def _should_report_module(path: Path, module: str) -> bool:
    if not _is_forbidden_module(module):
        return False

    route_domain = _app_route_domain(path)
    if route_domain is None:
        return True

    parts = tuple(part for part in _normalise_module(module).split(".") if part)
    if len(parts) >= 2 and parts[0] == "apps" and parts[1] == route_domain:
        return False
    return True


def _scan_file(path: Path) -> list[_Violation]:
    violations: list[_Violation] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError) as exc:
        logger.warning("router_guard: could not parse %s: %s", path, exc)
        return violations

    module_level_nodes = {
        id(node)
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    }
    deferred_nodes = {
        id(child)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for child in ast.walk(node)
        if isinstance(child, (ast.Import, ast.ImportFrom))
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _should_report_module(path, alias.name):
                    violations.append(
                        _Violation(
                            str(path),
                            node.lineno,
                            alias.name,
                            [alias.name],
                            id(node) in deferred_nodes and id(node) not in module_level_nodes,
                        )
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _should_report_module(path, module):
                violations.append(
                    _Violation(
                        str(path),
                        node.lineno,
                        module,
                        [alias.name for alias in node.names],
                        id(node) in deferred_nodes and id(node) not in module_level_nodes,
                    )
                )

    return violations


def _route_prefix_from_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith("_router"):
        stem = stem[: -len("_router")]
    return stem.replace("_", ".")


def guard_request(request: Any, route_prefix: str, user_context: dict[str, Any] | None = None) -> Any:
    """Delegate request-specific route policy to an app-registered guard."""
    guard_fn = get_route_guard(route_prefix)
    if guard_fn is None:
        return True
    return guard_fn(request=request, route_prefix=route_prefix, user_context=user_context or {})


def _candidate_scan_files(scan_dir: Path) -> list[Path]:
    if not scan_dir.is_dir():
        return []
    return sorted(path for path in scan_dir.glob("*.py") if not path.name.startswith("_"))


def validate_router_boundary(
    routes_dir: Path | None = None,
    *,
    include_app_routes: bool = True,
) -> None:
    """Scan platform entrypoints for generic boundary violations."""
    scan_dirs: list[Path] = []
    if routes_dir is None:
        scan_dirs.append(Path(__file__).parent.parent / "routes")
    else:
        scan_dirs.append(routes_dir)
    scan_dirs.append(Path(__file__).parent.parent / "db" / "dao")
    if include_app_routes:
        apps_dir = Path(__file__).parent.parent.parent / "apps"
        if apps_dir.is_dir():
            for route_dir in sorted(apps_dir.glob("*/routes")):
                if route_dir.is_dir():
                    scan_dirs.append(route_dir)

    scan_files: list[Path] = []
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            logger.warning("router_guard: scan directory not found at %s - skipping", scan_dir)
            continue
        scan_files.extend(_candidate_scan_files(scan_dir))

    if not scan_files:
        logger.warning("router_guard: no scan files found - skipping")
        return

    hard_violations: list[_Violation] = []
    soft_violations: list[_Violation] = []
    for py_file in scan_files:
        if py_file.parent.name == "routes":
            guard_fn = get_route_guard(_route_prefix_from_path(py_file))
            if guard_fn is not None:
                guard_fn(request=None, route_prefix=_route_prefix_from_path(py_file), user_context={})
        for violation in _scan_file(py_file):
            if violation.is_deferred:
                soft_violations.append(violation)
            else:
                hard_violations.append(violation)

    try:
        from AINDY.platform_layer.metrics import deferred_boundary_violations_total

        deferred_boundary_violations_total.set(len(soft_violations))
    except Exception:
        pass

    if soft_violations:
        logger.warning(
            "router_guard: %d deferred cross-domain import(s) detected "
            "(function-body imports; tracked as soft violations)",
            len(soft_violations),
        )
        for violation in soft_violations[:20]:
            logger.warning(
                "  [deferred] %s:%d  module=%r  names=%s",
                violation.file,
                violation.lineno,
                violation.module,
                violation.names,
            )
        if len(soft_violations) > 20:
            logger.warning("  ... and %d more", len(soft_violations) - 20)

    if not hard_violations:
        logger.info(
            "router_guard: PASS - %d files, %d deferred soft violations",
            len(scan_files),
            len(soft_violations),
        )
        return

    lines = ["RouterBoundaryViolation: platform files with forbidden direct implementation imports:"]
    for violation in hard_violations:
        rel = str(Path(violation.file))
        lines.append(
            f"  {rel}:{violation.lineno}  module={violation.module!r}  names={violation.names}"
        )
    raise RouterBoundaryViolation("\n".join(lines))

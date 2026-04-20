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


def _scan_file(path: Path) -> list[_Violation]:
    violations: list[_Violation] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError) as exc:
        logger.warning("router_guard: could not parse %s: %s", path, exc)
        return violations

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    violations.append(_Violation(str(path), node.lineno, alias.name, [alias.name]))

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_forbidden_module(module):
                violations.append(
                    _Violation(
                        str(path),
                        node.lineno,
                        module,
                        [alias.name for alias in node.names],
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


def validate_router_boundary(routes_dir: Path | None = None) -> None:
    """Scan platform entrypoints for generic boundary violations."""
    scan_dirs: list[Path] = []
    if routes_dir is None:
        scan_dirs.append(Path(__file__).parent.parent / "routes")
    else:
        scan_dirs.append(routes_dir)
    scan_dirs.append(Path(__file__).parent.parent / "db" / "dao")

    scan_files: list[Path] = []
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            logger.warning("router_guard: scan directory not found at %s - skipping", scan_dir)
            continue
        scan_files.extend(_candidate_scan_files(scan_dir))

    if not scan_files:
        logger.warning("router_guard: no scan files found - skipping")
        return

    all_violations: list[_Violation] = []
    for py_file in scan_files:
        if py_file.parent.name == "routes":
            guard_fn = get_route_guard(_route_prefix_from_path(py_file))
            if guard_fn is not None:
                guard_fn(request=None, route_prefix=_route_prefix_from_path(py_file), user_context={})
        all_violations.extend(_scan_file(py_file))

    if not all_violations:
        logger.info(
            "router_guard: PASS - %d files respect the generic routing boundary",
            len(scan_files),
        )
        return

    lines = ["RouterBoundaryViolation: platform files with forbidden direct implementation imports:"]
    for violation in all_violations:
        rel = str(Path(violation.file))
        lines.append(
            f"  {rel}:{violation.lineno}  module={violation.module!r}  names={violation.names}"
        )
    raise RouterBoundaryViolation("\n".join(lines))

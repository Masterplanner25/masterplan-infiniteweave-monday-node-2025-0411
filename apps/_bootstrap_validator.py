from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


class BootstrapDependencyError(Exception):
    pass


def _iter_bootstrap_files(bootstrap_dir: str) -> list[tuple[str, Path]]:
    root = Path(bootstrap_dir)
    files: list[tuple[str, Path]] = []
    for path in sorted(root.glob("*/bootstrap.py")):
        files.append((path.parent.name, path))
    return files


def _extract_list_assignment(tree: ast.AST, variable_name: str) -> list[str]:
    for node in getattr(tree, "body", []):
        value_node = None
        if isinstance(node, ast.Assign):
            if any(getattr(target, "id", None) == variable_name for target in node.targets):
                value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if getattr(node.target, "id", None) == variable_name:
                value_node = node.value
        if value_node is None:
            continue
        value = ast.literal_eval(value_node)
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            raise BootstrapDependencyError(
                f"{variable_name} must be a list or tuple literal."
            )
        return [str(item) for item in value]
    return []


def _extract_imported_app(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            if len(parts) >= 2 and parts[0] == "apps":
                return parts[1]
        return None
    if isinstance(node, ast.ImportFrom):
        if not node.module:
            return None
        parts = node.module.split(".")
        if len(parts) >= 2 and parts[0] == "apps":
            return parts[1]
    return None


def extract_declared_deps(bootstrap_dir: str) -> dict[str, list[str]]:
    declared: dict[str, list[str]] = {}
    for app_name, bootstrap_path in _iter_bootstrap_files(bootstrap_dir):
        tree = ast.parse(bootstrap_path.read_text(encoding="utf-8"), filename=str(bootstrap_path))
        declared[app_name] = _extract_list_assignment(tree, "APP_DEPENDS_ON")
    return declared


def extract_actual_top_level_imports(bootstrap_dir: str) -> dict[str, list[str]]:
    actual: dict[str, list[str]] = {}
    for app_name, bootstrap_path in _iter_bootstrap_files(bootstrap_dir):
        tree = ast.parse(bootstrap_path.read_text(encoding="utf-8"), filename=str(bootstrap_path))
        imports: list[str] = []
        for node in tree.body:
            imported_app = _extract_imported_app(node)
            if imported_app and imported_app != app_name and imported_app not in imports:
                imports.append(imported_app)
        actual[app_name] = imports
    return actual


def find_undeclared_dependencies(
    declared: dict[str, list[str]],
    actual: dict[str, list[str]],
) -> dict[str, list[str]]:
    undeclared: dict[str, list[str]] = {}
    for app_name in sorted(actual):
        declared_deps = set(declared.get(app_name, []))
        missing = sorted(dep for dep in actual.get(app_name, []) if dep not in declared_deps)
        if missing:
            undeclared[app_name] = missing
    return undeclared


def find_circular_dependencies(deps: dict[str, list[str]]) -> list[list[str]]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []
    cycle_keys: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for dependency in sorted(deps.get(node, [])):
            if dependency not in deps:
                continue
            if dependency in visiting:
                start_index = stack.index(dependency)
                cycle = stack[start_index:] + [dependency]
                key = tuple(cycle)
                if key not in cycle_keys:
                    cycle_keys.add(key)
                    cycles.append(cycle)
                continue
            visit(dependency)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(deps):
        visit(node)

    return cycles


def compute_boot_order(declared_deps: dict[str, list[str]]) -> list[str]:
    cycles = find_circular_dependencies(declared_deps)
    if cycles:
        formatted = "; ".join(" -> ".join(cycle) for cycle in cycles)
        raise BootstrapDependencyError(f"Circular dependencies detected: {formatted}")

    adjacency: dict[str, list[str]] = defaultdict(list)
    in_degree = {app_name: 0 for app_name in declared_deps}

    for app_name, dependencies in declared_deps.items():
        for dependency in sorted(set(dependencies)):
            if dependency not in in_degree:
                continue
            adjacency[dependency].append(app_name)
            in_degree[app_name] += 1

    ready = sorted(app_name for app_name, degree in in_degree.items() if degree == 0)
    order: list[str] = []

    while ready:
        node = ready.pop(0)
        order.append(node)
        for dependent in sorted(adjacency.get(node, [])):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)
                ready.sort()

    if len(order) != len(in_degree):
        raise BootstrapDependencyError("Unable to compute boot order due to a dependency cycle.")

    return order


def validate_bootstrap_deps(bootstrap_dir: str) -> None:
    declared = extract_declared_deps(bootstrap_dir)
    actual = extract_actual_top_level_imports(bootstrap_dir)
    undeclared = find_undeclared_dependencies(declared, actual)
    cycles = find_circular_dependencies(actual)

    if not undeclared and not cycles:
        return

    message_lines = ["Bootstrap validation failed:", ""]
    if undeclared:
        message_lines.append("UNDECLARED DEPENDENCIES:")
        for app_name in sorted(undeclared):
            message_lines.append(
                f"  {app_name}: imports {undeclared[app_name]} but does not declare them"
            )
        message_lines.append("")
    if cycles:
        message_lines.append("CIRCULAR DEPENDENCIES:")
        for cycle in cycles:
            message_lines.append(f"  Cycle detected: {' -> '.join(cycle)}")
        message_lines.append("")
    message_lines.append("Fix: update APP_DEPENDS_ON in each app's bootstrap.py.")
    raise BootstrapDependencyError("\n".join(message_lines))

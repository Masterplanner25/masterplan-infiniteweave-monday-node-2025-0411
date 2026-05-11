from __future__ import annotations

from collections import deque
from typing import Any


def resolve_boot_order(app_bootstraps: dict[str, Any]) -> list[str]:
    """Resolve a valid bootstrap order using Kahn's algorithm."""
    if not app_bootstraps:
        return []

    dependencies: dict[str, list[str]] = {}
    for app_name, module in app_bootstraps.items():
        raw_dependencies = getattr(module, "BOOTSTRAP_DEPENDS_ON", [])
        if raw_dependencies is None:
            raw_dependencies = []
        dependencies[app_name] = [str(dep) for dep in raw_dependencies]

    for app_name, declared_dependencies in dependencies.items():
        for dependency in declared_dependencies:
            if dependency not in app_bootstraps:
                raise RuntimeError(
                    f"App '{app_name}' declares dependency on '{dependency}' but no such app is registered."
                )

    adjacency: dict[str, list[str]] = {app_name: [] for app_name in app_bootstraps}
    indegree: dict[str, int] = {app_name: 0 for app_name in app_bootstraps}
    for app_name, declared_dependencies in dependencies.items():
        unique_dependencies = list(dict.fromkeys(declared_dependencies))
        indegree[app_name] = len(unique_dependencies)
        for dependency in unique_dependencies:
            adjacency[dependency].append(app_name)

    queue = deque(app_name for app_name in app_bootstraps if indegree[app_name] == 0)
    ordered: list[str] = []
    while queue:
        app_name = queue.popleft()
        ordered.append(app_name)
        for dependent in adjacency[app_name]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) == len(app_bootstraps):
        return ordered

    cycle = _find_cycle(dependencies, set(app_bootstraps) - set(ordered))
    if cycle:
        raise RuntimeError(f"Bootstrap dependency cycle detected: {' → '.join(cycle)}")
    raise RuntimeError("Bootstrap dependency cycle detected.")


def _find_cycle(dependencies: dict[str, list[str]], blocked_nodes: set[str]) -> list[str]:
    visited: set[str] = set()
    visiting: list[str] = []
    stack_index: dict[str, int] = {}

    def visit(node: str) -> list[str] | None:
        visited.add(node)
        stack_index[node] = len(visiting)
        visiting.append(node)
        for dependency in dependencies.get(node, []):
            if dependency not in blocked_nodes:
                continue
            if dependency in stack_index:
                cycle_start = stack_index[dependency]
                cycle = visiting[cycle_start:] + [dependency]
                return cycle
            if dependency not in visited:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        visiting.pop()
        stack_index.pop(node, None)
        return None

    for node in dependencies:
        if node in blocked_nodes and node not in visited:
            cycle = visit(node)
            if cycle:
                return cycle
    return []

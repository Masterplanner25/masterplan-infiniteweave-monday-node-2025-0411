from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from AINDY.kernel.errors import BootstrapDependencyError


class BootstrapManifest(Protocol):
    """What the plugin registry exposes after load_plugins() completes."""

    def get_registered_apps(self) -> list[str]: ...
    def get_bootstrap_dependencies(self) -> dict[str, list[str]]: ...
    def get_core_domains(self) -> list[str]: ...


def find_missing_dependencies(
    registered_apps: list[str],
    declared_deps: dict[str, list[str]],
) -> dict[str, list[str]]:
    known = set(registered_apps)
    missing: dict[str, list[str]] = {}
    for app_name in sorted(registered_apps):
        unresolved = sorted(
            dependency
            for dependency in declared_deps.get(app_name, [])
            if dependency not in known
        )
        if unresolved:
            missing[app_name] = unresolved
    return missing


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


def validate_bootstrap_manifest(manifest: BootstrapManifest) -> None:
    """
    Validate the loaded bootstrap dependency graph.

    Raises BootstrapDependencyError if core domains are missing, a declared
    dependency is missing, or the registered graph contains a cycle.
    """

    registered_apps = sorted({name for name in manifest.get_registered_apps() if isinstance(name, str)})
    declared_deps = {
        str(app_name): [str(dep) for dep in dependencies]
        for app_name, dependencies in manifest.get_bootstrap_dependencies().items()
        if isinstance(app_name, str)
    }
    core_domains = sorted({name for name in manifest.get_core_domains() if isinstance(name, str)})

    missing_core_domains = sorted(core for core in core_domains if core not in registered_apps)
    missing_dependencies = find_missing_dependencies(registered_apps, declared_deps)
    graph = {app_name: list(declared_deps.get(app_name, [])) for app_name in registered_apps}
    cycles = find_circular_dependencies(graph)

    if not missing_core_domains and not missing_dependencies and not cycles:
        return

    message_lines = ["Bootstrap validation failed:", ""]
    if missing_core_domains:
        message_lines.append("MISSING CORE DOMAINS:")
        message_lines.append(f"  Missing required core domains: {missing_core_domains}")
        message_lines.append("")
    if missing_dependencies:
        message_lines.append("MISSING DECLARED DEPENDENCIES:")
        for app_name in sorted(missing_dependencies):
            message_lines.append(
                f"  {app_name}: declares missing dependencies {missing_dependencies[app_name]}"
            )
        message_lines.append("")
    if cycles:
        message_lines.append("CIRCULAR DEPENDENCIES:")
        for cycle in cycles:
            message_lines.append(f"  Cycle detected: {' -> '.join(cycle)}")
        message_lines.append("")
    message_lines.append("Fix: update bootstrap dependency declarations for registered plugins.")
    raise BootstrapDependencyError("\n".join(message_lines))

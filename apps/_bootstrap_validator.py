from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from AINDY.kernel.errors import BootstrapDependencyError
from AINDY.platform_layer.bootstrap_contract import (
    compute_boot_order,
    find_circular_dependencies,
    validate_bootstrap_manifest,
)


class _BootstrapManifestAdapter:
    def __init__(
        self,
        *,
        registered_apps: list[str],
        dependencies: dict[str, list[str]],
        core_domains: list[str],
    ) -> None:
        self._registered_apps = list(registered_apps)
        self._dependencies = {
            str(app_name): list(deps) for app_name, deps in dependencies.items()
        }
        self._core_domains = list(core_domains)

    def get_registered_apps(self) -> list[str]:
        return list(self._registered_apps)

    def get_bootstrap_dependencies(self) -> dict[str, list[str]]:
        return {name: list(deps) for name, deps in self._dependencies.items()}

    def get_core_domains(self) -> list[str]:
        return list(self._core_domains)


def _manifest_from_apps_path(_apps_path: str | Path) -> _BootstrapManifestAdapter:
    apps_path = Path(_apps_path)
    if not apps_path.is_absolute():
        apps_path = Path(__file__).resolve().parent.parent / apps_path
    if not apps_path.exists():
        fallback = Path(__file__).resolve().parent
        if fallback.exists():
            apps_path = fallback

    registered_apps: list[str] = []
    dependencies: dict[str, list[str]] = {}

    for child in sorted(apps_path.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        bootstrap_path = child / "bootstrap.py"
        if not bootstrap_path.exists():
            continue

        registered_apps.append(child.name)
        declared_deps: list[str] = []
        try:
            tree = ast.parse(bootstrap_path.read_text(encoding="utf-8", errors="ignore"))
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if getattr(target, "id", None) == "BOOTSTRAP_DEPENDS_ON":
                            declared_deps = list(ast.literal_eval(node.value) or [])
                elif isinstance(node, ast.AnnAssign):
                    if getattr(node.target, "id", None) == "BOOTSTRAP_DEPENDS_ON":
                        declared_deps = list(ast.literal_eval(node.value) or [])
        except (SyntaxError, ValueError, TypeError):
            declared_deps = []
        dependencies[child.name] = [str(dep) for dep in declared_deps]

    return _BootstrapManifestAdapter(
        registered_apps=registered_apps,
        dependencies=dependencies,
        core_domains=["tasks", "identity", "agent"],
    )


def validate_bootstrap_deps(manifest_or_apps_path: Any) -> None:
    if hasattr(manifest_or_apps_path, "get_registered_apps"):
        validate_bootstrap_manifest(manifest_or_apps_path)
        return

    if isinstance(manifest_or_apps_path, (str, Path)):
        validate_bootstrap_manifest(_manifest_from_apps_path(manifest_or_apps_path))
        return

    raise TypeError(
        "validate_bootstrap_deps() expects a bootstrap manifest or the legacy apps path"
    )

__all__ = [
    "BootstrapDependencyError",
    "compute_boot_order",
    "find_circular_dependencies",
    "validate_bootstrap_deps",
]

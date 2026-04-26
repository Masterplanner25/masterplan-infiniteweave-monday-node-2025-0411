from __future__ import annotations

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
    # Path is kept for backward compatibility with the legacy validator API.
    import apps.bootstrap as app_bootstrap

    metadata = app_bootstrap._load_bootstrap_metadata()
    return _BootstrapManifestAdapter(
        registered_apps=list(app_bootstrap.APP_BOOTSTRAP_MODULES),
        dependencies={
            app_name: list(data.get("BOOTSTRAP_DEPENDS_ON", []))
            for app_name, data in metadata.items()
        },
        core_domains=list(app_bootstrap.CORE_DOMAINS_SET),
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

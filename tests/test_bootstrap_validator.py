from __future__ import annotations

import importlib

import pytest

from apps._bootstrap_validator import validate_bootstrap_deps
from AINDY.kernel.errors import BootstrapDependencyError
from AINDY.platform_layer.bootstrap_contract import (
    compute_boot_order,
    find_circular_dependencies,
    validate_bootstrap_manifest,
)


class _Manifest:
    def __init__(
        self,
        *,
        registered_apps: list[str],
        dependencies: dict[str, list[str]],
        core_domains: list[str] | None = None,
    ) -> None:
        self._registered_apps = registered_apps
        self._dependencies = dependencies
        self._core_domains = core_domains or ["tasks", "identity", "agent"]

    def get_registered_apps(self) -> list[str]:
        return list(self._registered_apps)

    def get_bootstrap_dependencies(self) -> dict[str, list[str]]:
        return {name: list(deps) for name, deps in self._dependencies.items()}

    def get_core_domains(self) -> list[str]:
        return list(self._core_domains)


def test_current_registered_bootstrap_manifest_is_valid() -> None:
    import AINDY.startup as startup

    validate_bootstrap_manifest(startup.registry)


def test_legacy_apps_path_validator_entry_point_is_valid() -> None:
    validate_bootstrap_deps("apps")


def test_missing_declared_dependency_raises_bootstrap_error() -> None:
    manifest = _Manifest(
        registered_apps=["tasks", "analytics", "identity", "agent"],
        dependencies={
            "tasks": [],
            "analytics": ["identity", "missing_app"],
            "identity": [],
            "agent": [],
        },
    )

    with pytest.raises(BootstrapDependencyError, match="missing_app"):
        validate_bootstrap_manifest(manifest)


def test_missing_core_domain_raises_bootstrap_error() -> None:
    manifest = _Manifest(
        registered_apps=["tasks", "analytics"],
        dependencies={"tasks": [], "analytics": []},
        core_domains=["tasks", "identity", "agent"],
    )

    with pytest.raises(BootstrapDependencyError, match="identity"):
        validate_bootstrap_manifest(manifest)


def test_circular_dependency_detected() -> None:
    cycles = find_circular_dependencies({"A": ["B"], "B": ["A"]})
    assert ["A", "B", "A"] in cycles or ["B", "A", "B"] in cycles


def test_topological_sort_respects_deps() -> None:
    order = compute_boot_order({"C": ["A", "B"], "B": ["A"], "A": []})

    assert order.index("A") < order.index("B") < order.index("C")


def test_topological_sort_raises_on_cycle() -> None:
    with pytest.raises(BootstrapDependencyError, match="Circular dependencies detected"):
        compute_boot_order({"A": ["B"], "B": ["A"]})


def test_startup_fails_if_bootstrap_manifest_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    import AINDY.startup as startup
    import AINDY.platform_layer.bootstrap_contract as bootstrap_contract

    original = bootstrap_contract.validate_bootstrap_manifest

    def _raise(_manifest) -> None:
        raise BootstrapDependencyError("forced bootstrap validation failure")

    monkeypatch.setattr(bootstrap_contract, "validate_bootstrap_manifest", _raise)
    try:
        with pytest.raises(RuntimeError, match="forced bootstrap validation failure"):
            importlib.reload(startup)
    finally:
        monkeypatch.setattr(bootstrap_contract, "validate_bootstrap_manifest", original)
        importlib.reload(startup)

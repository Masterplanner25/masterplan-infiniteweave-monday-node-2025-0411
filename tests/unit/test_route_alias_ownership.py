from __future__ import annotations

import importlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_repo_root_routes_aliases_are_runtime_owned_only():
    import routes

    aliases = getattr(routes, "_ROUTE_ALIASES")
    assert aliases
    assert all(target.startswith("AINDY.routes.") for target in aliases.values()), aliases


def test_repo_root_routes_has_no_app_owned_shim_files():
    route_dir = ROOT / "routes"
    python_files = sorted(path.name for path in route_dir.glob("*.py"))

    assert python_files == ["__init__.py", "watcher_router.py"]


def test_repo_root_routes_rejects_removed_app_aliases():
    import routes

    with pytest.raises(AttributeError):
        getattr(routes, "task_router")
    with pytest.raises(AttributeError):
        getattr(routes, "leadgen_router")
    with pytest.raises(AttributeError):
        getattr(routes, "score_router")
    with pytest.raises(AttributeError):
        getattr(routes, "legacy_surface_router")


def test_repo_root_runtime_alias_imports_without_app_modules():
    module = importlib.import_module("routes")
    watcher_module = getattr(module, "watcher_router")

    assert watcher_module.__name__ == "AINDY.routes.watcher_router"

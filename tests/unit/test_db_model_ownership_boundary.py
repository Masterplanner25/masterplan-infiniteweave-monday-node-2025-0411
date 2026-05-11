from __future__ import annotations

import builtins
import sys

import pytest

from tests.helpers.app_profile import bootstrap_app_models
from tests.helpers.runtime import (
    clear_boot_profile_env,
    import_runtime_model_registry,
    set_runtime_only_boot_mode,
)


def _hide_apps_bootstrap(monkeypatch):
    real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"apps", "apps.bootstrap"}:
            missing = "apps.bootstrap" if name == "apps.bootstrap" else "apps"
            raise ModuleNotFoundError(f"No module named '{missing}'", name=missing)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)


@pytest.mark.runtime_only
def test_runtime_model_registry_imports_without_apps_bootstrap(monkeypatch):
    original_apps_module = sys.modules.pop("apps", None)
    original_apps_bootstrap_module = sys.modules.pop("apps.bootstrap", None)
    _hide_apps_bootstrap(monkeypatch)
    set_runtime_only_boot_mode()
    try:
        import_runtime_model_registry()

        from AINDY.db.database import Base

        assert "users" in Base.metadata.tables
        assert "agent_runs" in Base.metadata.tables
        assert "apps.bootstrap" not in sys.modules
    finally:
        clear_boot_profile_env()
        if original_apps_module is not None:
            sys.modules["apps"] = original_apps_module
        if original_apps_bootstrap_module is not None:
            sys.modules["apps.bootstrap"] = original_apps_bootstrap_module


@pytest.mark.app_profile
def test_app_bootstrap_extends_runtime_metadata_with_app_models():
    clear_boot_profile_env()
    import_runtime_model_registry()
    bootstrap_app_models(required=True)

    from AINDY.db.database import Base

    assert "users" in Base.metadata.tables
    assert "agent_runs" in Base.metadata.tables
    assert "tasks" in Base.metadata.tables
    assert "master_plans" in Base.metadata.tables

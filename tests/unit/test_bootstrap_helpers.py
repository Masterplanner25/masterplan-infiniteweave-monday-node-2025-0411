from __future__ import annotations

import builtins

import pytest

from tests.helpers import app_profile
from tests.helpers import bootstrap as bootstrap_shim
from tests.helpers import runtime


pytestmark = pytest.mark.runtime_only


def _hide_apps_bootstrap(monkeypatch):
    real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"apps", "apps.bootstrap"}:
            missing = "apps.bootstrap" if name == "apps.bootstrap" else "apps"
            raise ModuleNotFoundError(f"No module named '{missing}'", name=missing)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)


def test_apps_bootstrap_available_is_false_without_apps_tree(monkeypatch):
    _hide_apps_bootstrap(monkeypatch)

    assert app_profile.apps_bootstrap_available() is False


def test_bootstrap_app_models_returns_false_when_apps_bootstrap_is_missing(monkeypatch):
    _hide_apps_bootstrap(monkeypatch)

    assert app_profile.bootstrap_app_models(required=False) is False


def test_reset_app_bootstrap_state_returns_false_when_apps_bootstrap_is_missing(monkeypatch):
    _hide_apps_bootstrap(monkeypatch)

    assert app_profile.reset_app_bootstrap_state(required=False) is False


def test_bootstrap_app_models_skips_when_apps_bootstrap_is_required(monkeypatch):
    _hide_apps_bootstrap(monkeypatch)

    with pytest.raises(pytest.skip.Exception, match="apps\\.bootstrap"):
        app_profile.bootstrap_app_models(required=True)


def test_reset_app_bootstrap_state_skips_when_apps_bootstrap_is_required(monkeypatch):
    _hide_apps_bootstrap(monkeypatch)

    with pytest.raises(pytest.skip.Exception, match="apps\\.bootstrap"):
        app_profile.reset_app_bootstrap_state(required=True)


def test_bootstrap_shim_reexports_split_helper_modules():
    assert bootstrap_shim.bootstrap_app_models is app_profile.bootstrap_app_models
    assert bootstrap_shim.reset_app_bootstrap_state is app_profile.reset_app_bootstrap_state
    assert bootstrap_shim.import_runtime_model_registry is runtime.import_runtime_model_registry
    assert bootstrap_shim.set_runtime_only_boot_mode is runtime.set_runtime_only_boot_mode

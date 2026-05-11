from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from AINDY.platform_layer import registry


pytestmark = pytest.mark.app_profile

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _reset_plugin_registry_state(monkeypatch):
    original_apps_module = sys.modules.get("apps")
    original_apps_bootstrap_module = sys.modules.get("apps.bootstrap")
    registry._loaded_plugins.clear()
    registry._active_plugin_profile = None
    registry._active_plugin_profile_source = None
    yield
    registry._loaded_plugins.clear()
    registry._active_plugin_profile = None
    registry._active_plugin_profile_source = None
    if original_apps_module is None:
        sys.modules.pop("apps", None)
    else:
        sys.modules["apps"] = original_apps_module
    if original_apps_bootstrap_module is None:
        sys.modules.pop("apps.bootstrap", None)
    else:
        sys.modules["apps.bootstrap"] = original_apps_bootstrap_module
    monkeypatch.delenv("AINDY_BOOT_MODE", raising=False)
    monkeypatch.delenv("AINDY_BOOT_PROFILE", raising=False)
    monkeypatch.delenv("AINDY_PLUGIN_PROFILE", raising=False)
    monkeypatch.delenv("AINDY_PLUGIN_MANIFEST", raising=False)
    monkeypatch.delenv("AINDY_APP_PLUGIN_MANIFEST", raising=False)


def test_repo_root_app_manifest_is_the_default_app_profile():
    profile_name, plugins = registry.resolve_plugin_profile(ROOT / "aindy_plugins.json")

    assert profile_name == "default-apps"
    assert plugins == ["apps.bootstrap"]


def test_runtime_loader_can_boot_apps_bootstrap_from_apps_repo(monkeypatch):
    import apps.bootstrap as apps_bootstrap

    apps_bootstrap._BOOTSTRAPPED = False
    apps_bootstrap._DEGRADED_DOMAINS = []
    registry._registered_apps.clear()
    registry._bootstrap_dependencies.clear()
    registry.publish_degraded_domains(())
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: ROOT / "aindy_plugins.json")

    loaded = registry.load_plugins()
    imported = importlib.import_module("apps.bootstrap")

    assert loaded == ["apps.bootstrap"]
    assert imported is apps_bootstrap
    assert apps_bootstrap._BOOTSTRAPPED is True

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from AINDY.platform_layer import registry

RUNTIME_ONLY = pytest.mark.runtime_only
APP_PROFILE = pytest.mark.app_profile


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


def _write_fake_plugin_module(tmp_path: Path, module_name: str, *, boot_order: list[str] | None = None) -> None:
    (tmp_path / f"{module_name}.py").write_text(
        "\n".join(
            [
                "BOOTSTRAP_CALLS = []",
                "",
                "def bootstrap():",
                f"    BOOTSTRAP_CALLS.append({module_name!r})",
                "",
                "def get_resolved_boot_order():",
                f"    return {boot_order or [module_name]!r}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_fake_apps_bootstrap_package(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("", encoding="utf-8")
    (apps_dir / "bootstrap.py").write_text(
        "\n".join(
            [
                "BOOTSTRAP_CALLS = []",
                "",
                "def bootstrap():",
                "    BOOTSTRAP_CALLS.append('apps.bootstrap')",
                "",
                "def get_resolved_boot_order():",
                "    return ['apps.bootstrap']",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _import_fake_plugin(module_name: str):
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


@RUNTIME_ONLY
def test_resolve_plugin_profile_uses_default_profile(tmp_path):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )

    profile_name, plugins = registry.resolve_plugin_profile(manifest)

    assert profile_name == "default-apps"
    assert plugins == ["apps.bootstrap"]


@RUNTIME_ONLY
def test_resolve_plugin_profile_prefers_default_app_manifest_when_present(tmp_path, monkeypatch):
    app_manifest = tmp_path / "aindy_plugins.json"
    runtime_manifest = tmp_path / "runtime_plugins.json"
    app_manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    runtime_manifest.write_text(
        """
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: app_manifest)
    monkeypatch.setattr(registry, "_default_runtime_manifest_path", lambda: runtime_manifest)

    profile_name, plugins = registry.resolve_plugin_profile()

    assert profile_name == "default-apps"
    assert plugins == ["apps.bootstrap"]


@RUNTIME_ONLY
def test_load_plugins_can_select_platform_only_via_env(tmp_path, monkeypatch):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AINDY_BOOT_PROFILE", "platform-only")

    loaded = registry.load_plugins(manifest)
    boot_order = registry.get_plugin_boot_order(manifest)

    assert loaded == []
    assert boot_order == []


@RUNTIME_ONLY
def test_runtime_manifest_is_used_for_runtime_only_selection(tmp_path, monkeypatch):
    app_manifest = tmp_path / "aindy_plugins.json"
    runtime_manifest = tmp_path / "runtime_plugins.json"
    app_manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["missing.bootstrap.module"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    runtime_manifest.write_text(
        """
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: app_manifest)
    monkeypatch.setattr(registry, "_default_runtime_manifest_path", lambda: runtime_manifest)
    monkeypatch.setenv("AINDY_BOOT_MODE", "runtime-only")

    profile_name, plugins = registry.resolve_plugin_profile()
    loaded = registry.load_plugins()
    boot_order = registry.get_plugin_boot_order()

    assert profile_name == "platform-only"
    assert plugins == []
    assert loaded == []
    assert boot_order == []


@RUNTIME_ONLY
def test_runtime_manifest_becomes_default_when_app_manifest_is_absent(tmp_path, monkeypatch):
    runtime_manifest = tmp_path / "runtime_plugins.json"
    runtime_manifest.write_text(
        """
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: tmp_path / "missing-app-manifest.json")
    monkeypatch.setattr(registry, "_default_runtime_manifest_path", lambda: runtime_manifest)

    profile_name, plugins = registry.resolve_plugin_profile()
    loaded = registry.load_plugins()
    boot_order = registry.get_plugin_boot_order()

    assert profile_name == "platform-only"
    assert plugins == []
    assert loaded == []
    assert boot_order == []


@RUNTIME_ONLY
def test_load_plugins_can_select_runtime_only_via_boot_mode(tmp_path, monkeypatch):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AINDY_BOOT_MODE", "runtime-only")

    profile_name, plugins = registry.resolve_plugin_profile(manifest)
    loaded = registry.load_plugins(manifest)
    boot_order = registry.get_plugin_boot_order(manifest)

    assert profile_name == "platform-only"
    assert plugins == []
    assert loaded == []
    assert boot_order == []
    assert registry.get_active_plugin_profile_source() == "AINDY_BOOT_MODE"


@APP_PROFILE
def test_explicit_app_profile_uses_app_manifest(tmp_path, monkeypatch):
    _write_fake_plugin_module(tmp_path, "app_profile_bootstrap_test")
    monkeypatch.syspath_prepend(str(tmp_path))

    app_manifest = tmp_path / "aindy_plugins.json"
    runtime_manifest = tmp_path / "runtime_plugins.json"
    app_manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["app_profile_bootstrap_test"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    runtime_manifest.write_text(
        """
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: app_manifest)
    monkeypatch.setattr(registry, "_default_runtime_manifest_path", lambda: runtime_manifest)
    monkeypatch.setenv("AINDY_BOOT_PROFILE", "default-apps")

    profile_name, plugins = registry.resolve_plugin_profile()
    loaded = registry.load_plugins()
    module = _import_fake_plugin("app_profile_bootstrap_test")

    assert profile_name == "default-apps"
    assert plugins == ["app_profile_bootstrap_test"]
    assert loaded == ["app_profile_bootstrap_test"]
    assert module.BOOTSTRAP_CALLS == ["app_profile_bootstrap_test"]


@APP_PROFILE
def test_default_app_profile_loads_app_owned_apps_bootstrap_plugin(tmp_path, monkeypatch):
    _write_fake_apps_bootstrap_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("apps.bootstrap", None)
    sys.modules.pop("apps", None)

    app_manifest = tmp_path / "aindy_plugins.json"
    runtime_manifest = tmp_path / "runtime_plugins.json"
    app_manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    runtime_manifest.write_text(
        """
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: app_manifest)
    monkeypatch.setattr(registry, "_default_runtime_manifest_path", lambda: runtime_manifest)

    loaded = registry.load_plugins()
    module = _import_fake_plugin("apps.bootstrap")

    assert loaded == ["apps.bootstrap"]
    assert module.BOOTSTRAP_CALLS == ["apps.bootstrap"]


@RUNTIME_ONLY
def test_explicit_boot_profile_overrides_runtime_only_boot_mode(tmp_path, monkeypatch):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AINDY_BOOT_MODE", "runtime-only")
    monkeypatch.setenv("AINDY_BOOT_PROFILE", "default-apps")

    profile_name, plugins = registry.resolve_plugin_profile(manifest)

    assert profile_name == "default-apps"
    assert plugins == ["apps.bootstrap"]


@RUNTIME_ONLY
def test_invalid_boot_mode_is_rejected(tmp_path, monkeypatch):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AINDY_BOOT_MODE", "surprise-mode")

    with pytest.raises(ValueError, match="AINDY_BOOT_MODE"):
        registry.resolve_plugin_profile(manifest)


@APP_PROFILE
def test_missing_app_manifest_fails_for_explicit_app_profile(tmp_path, monkeypatch):
    runtime_manifest = tmp_path / "runtime_plugins.json"
    runtime_manifest.write_text(
        """
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_default_app_manifest_path", lambda: tmp_path / "missing-app-manifest.json")
    monkeypatch.setattr(registry, "_default_runtime_manifest_path", lambda: runtime_manifest)
    monkeypatch.setenv("AINDY_BOOT_PROFILE", "default-apps")

    with pytest.raises(RuntimeError, match="default-apps"):
        registry.resolve_plugin_profile()


@RUNTIME_ONLY
def test_default_profile_with_zero_plugins_fails_unless_explicitly_selected(tmp_path):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": []}
  }
}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="default-apps"):
        registry.load_plugins(manifest)

    with pytest.raises(RuntimeError, match="default-apps"):
        registry.get_plugin_boot_order(manifest)


@RUNTIME_ONLY
def test_explicit_zero_plugin_profile_is_allowed(tmp_path):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )

    loaded = registry.load_plugins(manifest, profile="platform-only")
    boot_order = registry.get_plugin_boot_order(manifest, profile="platform-only")

    assert loaded == []
    assert boot_order == []


@RUNTIME_ONLY
def test_load_plugins_supports_runtime_owned_profiles(tmp_path, monkeypatch):
    _write_fake_plugin_module(
        tmp_path,
        "runtime_bootstrap_profile_test",
        boot_order=["domain.alpha", "domain.beta"],
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["runtime_bootstrap_profile_test"]}
  }
}
""".strip(),
        encoding="utf-8",
    )

    loaded = registry.load_plugins(manifest)
    boot_order = registry.get_plugin_boot_order(manifest)
    module = _import_fake_plugin("runtime_bootstrap_profile_test")

    assert loaded == ["runtime_bootstrap_profile_test"]
    assert module.BOOTSTRAP_CALLS == ["runtime_bootstrap_profile_test"]
    assert boot_order == ["domain.alpha", "domain.beta"]


@RUNTIME_ONLY
def test_missing_requested_plugin_fails_explicitly(tmp_path):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["missing.bootstrap.module"]}
  }
}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing\\.bootstrap\\.module"):
        registry.load_plugins(manifest)

    with pytest.raises(RuntimeError, match="missing\\.bootstrap\\.module"):
        registry.get_plugin_boot_order(manifest)


@RUNTIME_ONLY
def test_load_plugins_supports_legacy_manifest_shape(tmp_path, monkeypatch):
    _write_fake_plugin_module(tmp_path, "legacy_bootstrap_profile_test")
    monkeypatch.syspath_prepend(str(tmp_path))

    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "plugins": ["legacy_bootstrap_profile_test"]
}
""".strip(),
        encoding="utf-8",
    )

    profile_name, plugins = registry.resolve_plugin_profile(manifest)
    loaded = registry.load_plugins(manifest)
    module = _import_fake_plugin("legacy_bootstrap_profile_test")

    assert profile_name == "__legacy__"
    assert plugins == ["legacy_bootstrap_profile_test"]
    assert loaded == ["legacy_bootstrap_profile_test"]
    assert module.BOOTSTRAP_CALLS == ["legacy_bootstrap_profile_test"]


@RUNTIME_ONLY
def test_resolve_plugin_profile_rejects_unknown_profile(tmp_path):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["apps.bootstrap"]}
  }
}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing-profile"):
        registry.resolve_plugin_profile(manifest, profile="missing-profile")

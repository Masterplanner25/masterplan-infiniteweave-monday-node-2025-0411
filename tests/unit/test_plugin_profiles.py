from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from AINDY.platform_layer import registry


@pytest.fixture(autouse=True)
def _reset_plugin_registry_state(monkeypatch):
    registry._loaded_plugins.clear()
    yield
    registry._loaded_plugins.clear()
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


def _import_fake_plugin(module_name: str):
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


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

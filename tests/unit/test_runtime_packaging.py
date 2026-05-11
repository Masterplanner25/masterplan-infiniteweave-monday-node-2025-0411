from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from AINDY.platform_layer import registry


pytestmark = pytest.mark.runtime_only

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_package_metadata_declares_console_entrypoints():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "aindy-runtime"
    assert pyproject["project"]["scripts"] == {
        "aindy-runtime": "AINDY.runtime_only:main",
        "aindy-runtime-api": "AINDY.main:main",
    }
    assert pyproject["tool"]["setuptools"]["package-data"]["AINDY"] == ["*.json"]


def test_default_app_manifest_prefers_working_directory_for_installed_runtime(monkeypatch, tmp_path):
    apps_repo = tmp_path / "apps-repo"
    nested_workdir = apps_repo / "services" / "api"
    nested_workdir.mkdir(parents=True)
    app_manifest = apps_repo / "aindy_plugins.json"
    app_manifest.write_text('{"profiles": {"default-apps": {"plugins": ["apps.bootstrap"]}}}', encoding="utf-8")

    monkeypatch.chdir(nested_workdir)
    monkeypatch.setattr(
        registry,
        "_source_checkout_app_manifest_path",
        lambda: tmp_path / "missing-source-manifest.json",
    )

    assert registry._default_app_manifest_path() == app_manifest

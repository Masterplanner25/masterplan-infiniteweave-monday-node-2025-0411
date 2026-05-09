from __future__ import annotations

import os

import pytest


def import_runtime_model_registry() -> None:
    import AINDY.db.model_registry  # noqa: F401
    import AINDY.memory.memory_persistence  # noqa: F401


def _load_apps_bootstrap():
    try:
        import apps.bootstrap as apps_bootstrap
    except ModuleNotFoundError as exc:
        if exc.name in {"apps", "apps.bootstrap"}:
            return None
        raise
    return apps_bootstrap


def bootstrap_app_models(*, required: bool) -> bool:
    apps_bootstrap = _load_apps_bootstrap()
    if apps_bootstrap is None:
        if required:
            pytest.skip("app-profile test requires apps.bootstrap")
        return False
    apps_bootstrap.bootstrap_models()
    return True


def reset_app_bootstrap_state(*, required: bool) -> bool:
    apps_bootstrap = _load_apps_bootstrap()
    if apps_bootstrap is None:
        if required:
            pytest.skip("app-profile test requires apps.bootstrap")
        return False
    apps_bootstrap._BOOTSTRAPPED = False
    apps_bootstrap._DEGRADED_DOMAINS = []
    return True


def set_runtime_only_boot_mode() -> None:
    os.environ["AINDY_BOOT_MODE"] = "runtime-only"
    os.environ.pop("AINDY_BOOT_PROFILE", None)
    os.environ.pop("AINDY_PLUGIN_PROFILE", None)


def clear_boot_profile_env() -> None:
    os.environ.pop("AINDY_BOOT_MODE", None)
    os.environ.pop("AINDY_BOOT_PROFILE", None)
    os.environ.pop("AINDY_PLUGIN_PROFILE", None)

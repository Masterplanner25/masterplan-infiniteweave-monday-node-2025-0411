from __future__ import annotations

import pytest


APP_PROFILE_SKIP_REASON = "app-profile test requires app-owned apps.bootstrap plugin"


def _load_apps_bootstrap():
    try:
        import apps.bootstrap as apps_bootstrap
    except ModuleNotFoundError as exc:
        if exc.name in {"apps", "apps.bootstrap"}:
            return None
        raise
    return apps_bootstrap


def apps_bootstrap_available() -> bool:
    return _load_apps_bootstrap() is not None


def bootstrap_app_models(*, required: bool) -> bool:
    apps_bootstrap = _load_apps_bootstrap()
    if apps_bootstrap is None:
        if required:
            pytest.skip(APP_PROFILE_SKIP_REASON)
        return False
    apps_bootstrap.bootstrap_models()
    return True


def reset_app_bootstrap_state(*, required: bool) -> bool:
    apps_bootstrap = _load_apps_bootstrap()
    if apps_bootstrap is None:
        if required:
            pytest.skip(APP_PROFILE_SKIP_REASON)
        return False
    apps_bootstrap._BOOTSTRAPPED = False
    apps_bootstrap._DEGRADED_DOMAINS = []
    return True

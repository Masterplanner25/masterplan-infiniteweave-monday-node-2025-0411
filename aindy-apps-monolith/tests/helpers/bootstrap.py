"""Transitional helper shim.

Prefer importing from ``tests.helpers.runtime`` for runtime-only helpers and
``tests.helpers.app_profile`` for helpers that require the app-owned bootstrap
path. This module remains as a compatibility re-export during the monolith to
two-repo transition.
"""

from __future__ import annotations

from tests.helpers.app_profile import (
    APP_PROFILE_SKIP_REASON,
    apps_bootstrap_available,
    bootstrap_app_models,
    reset_app_bootstrap_state,
)
from tests.helpers.runtime import (
    clear_boot_profile_env,
    import_runtime_model_registry,
    set_runtime_only_boot_mode,
)

__all__ = [
    "APP_PROFILE_SKIP_REASON",
    "apps_bootstrap_available",
    "bootstrap_app_models",
    "clear_boot_profile_env",
    "import_runtime_model_registry",
    "reset_app_bootstrap_state",
    "set_runtime_only_boot_mode",
]

from __future__ import annotations

import os


def import_runtime_model_registry() -> None:
    import AINDY.db.model_registry  # noqa: F401
    import AINDY.memory.memory_persistence  # noqa: F401


def set_runtime_only_boot_mode() -> None:
    os.environ["AINDY_BOOT_MODE"] = "runtime-only"
    os.environ.pop("AINDY_BOOT_PROFILE", None)
    os.environ.pop("AINDY_PLUGIN_PROFILE", None)


def clear_boot_profile_env() -> None:
    os.environ.pop("AINDY_BOOT_MODE", None)
    os.environ.pop("AINDY_BOOT_PROFILE", None)
    os.environ.pop("AINDY_PLUGIN_PROFILE", None)

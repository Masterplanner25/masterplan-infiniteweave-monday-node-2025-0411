from __future__ import annotations

import os

from AINDY.platform_layer.deployment_contract import BOOT_MODE_ENV_VAR, RUNTIME_ONLY_BOOT_MODE

os.environ.setdefault(BOOT_MODE_ENV_VAR, RUNTIME_ONLY_BOOT_MODE)

from AINDY.main import app  # noqa: E402,F401

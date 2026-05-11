from __future__ import annotations

import os
from typing import NoReturn

from AINDY.platform_layer.deployment_contract import BOOT_MODE_ENV_VAR, RUNTIME_ONLY_BOOT_MODE

os.environ.setdefault(BOOT_MODE_ENV_VAR, RUNTIME_ONLY_BOOT_MODE)

from AINDY.main import app  # noqa: E402,F401


def main() -> NoReturn:
    import uvicorn

    uvicorn.run(
        "AINDY.runtime_only:app",
        host=os.getenv("AINDY_HOST", "127.0.0.1"),
        port=int(os.getenv("AINDY_PORT", "8000")),
    )
    raise SystemExit(0)


if __name__ == "__main__":
    main()

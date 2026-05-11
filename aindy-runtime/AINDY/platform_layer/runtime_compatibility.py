from __future__ import annotations

from AINDY._version import __version__ as RUNTIME_PACKAGE_VERSION
from AINDY.config import settings


RUNTIME_PACKAGE_NAME = "aindy-runtime"
COMPATIBILITY_DECLARATION_FORMAT = "pep440"


def _major_series(version: str) -> str:
    parts = (version or "0.0.0").split(".")
    major = parts[0] if parts and parts[0].isdigit() else "0"
    return f">={major}.0,<{int(major) + 1}.0"


def runtime_repo_compatibility_metadata() -> dict[str, object]:
    runtime_version = RUNTIME_PACKAGE_VERSION
    api_version = settings.API_VERSION
    return {
        "runtime_package": {
            "name": RUNTIME_PACKAGE_NAME,
            "version": runtime_version,
        },
        "apps_repo_contract": {
            "declaration_format": COMPATIBILITY_DECLARATION_FORMAT,
            "recommended_runtime_requirement": _major_series(runtime_version),
            "compatible_runtime_major": runtime_version.split(".")[0],
            "compatible_api_major": api_version.split(".")[0],
            "policy": (
                "The apps repo must declare a normal Python dependency range on "
                "aindy-runtime with an explicit upper bound before the next MAJOR "
                "runtime release. Runtime package MAJOR and API MAJOR indicate "
                "repo-split compatibility boundaries."
            ),
        },
    }

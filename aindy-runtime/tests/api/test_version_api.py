import pytest

from AINDY._version import __version__ as RUNTIME_PACKAGE_VERSION
from AINDY.platform_layer.deployment_contract import publish_api_runtime_state


pytestmark = pytest.mark.runtime_only


def test_version_route_includes_runtime_surface(runtime_only_client):
    publish_api_runtime_state(
        boot_mode="runtime-only",
        boot_profile="platform-only",
        boot_profile_source="AINDY_BOOT_MODE",
        app_plugins_loaded=False,
        app_plugin_count=0,
    )

    response = runtime_only_client.get("/api/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"] == {
        "boot_mode": "runtime-only",
        "boot_profile": "platform-only",
        "boot_profile_source": "AINDY_BOOT_MODE",
        "app_plugins_loaded": False,
        "app_plugin_count": 0,
        "ui_mode": "runtime-only",
        "default_route": "/memory",
        "platform_home": "/platform/agent",
    }
    assert payload["compatibility"] == {
        "runtime_package": {
            "name": "aindy-runtime",
            "version": RUNTIME_PACKAGE_VERSION,
        },
        "apps_repo_contract": {
            "declaration_format": "pep440",
            "recommended_runtime_requirement": ">=1.0,<2.0",
            "compatible_runtime_major": "1",
            "compatible_api_major": "1",
            "policy": (
                "The apps repo must declare a normal Python dependency range on "
                "aindy-runtime with an explicit upper bound before the next MAJOR "
                "runtime release. Runtime package MAJOR and API MAJOR indicate "
                "repo-split compatibility boundaries."
            ),
        },
    }

from AINDY.platform_layer.deployment_contract import publish_api_runtime_state


def test_version_route_includes_runtime_surface(client):
    publish_api_runtime_state(
        boot_mode="runtime-only",
        boot_profile="platform-only",
        boot_profile_source="AINDY_BOOT_MODE",
        app_plugins_loaded=False,
        app_plugin_count=0,
    )

    response = client.get("/api/version")

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

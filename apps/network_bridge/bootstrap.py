"""Network bridge domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = ["authorship"]
APP_DEPENDS_ON: list[str] = ["analytics", "authorship", "rippletrace"]


def register() -> None:
    _register_router()
    _register_response_adapters()
    _register_health_check()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.network_bridge.routes.network_bridge_router import router as network_bridge_router
    register_router(network_bridge_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter
    register_response_adapter("network_bridge", raw_json_adapter)


def _register_health_check() -> None:
    from AINDY.platform_layer.registry import register_health_check

    register_health_check("network_bridge", lambda: {"status": "ok"})

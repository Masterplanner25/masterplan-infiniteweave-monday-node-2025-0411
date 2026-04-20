"""Network bridge domain bootstrap."""
from __future__ import annotations


def register() -> None:
    _register_router()
    _register_response_adapters()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.network_bridge.routes.network_bridge_router import router as network_bridge_router
    register_router(network_bridge_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from apps._adapters import raw_json_adapter
    register_response_adapter("network_bridge", raw_json_adapter)

"""Dashboard domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []
APP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_routers()
    _register_route_prefixes()
    _register_response_adapters()
    _register_flow_results()


def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.dashboard.routes.dashboard_router import router as dashboard_router
    from apps.dashboard.routes.health_dashboard_router import router as health_dashboard_router

    register_router(dashboard_router)
    register_router(health_dashboard_router)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix
    register_route_prefix("dashboard", "task")


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter
    register_response_adapter("health", raw_json_adapter)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "dashboard_overview": "dashboard_overview_result",
        "health_dashboard_list": "health_dashboard_list_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

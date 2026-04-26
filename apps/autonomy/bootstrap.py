"""Autonomy domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []
APP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_router()
    _register_response_adapters()
    _register_flow_results()
    _register_health_check()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.autonomy.routes.autonomy_router import router as autonomy_router
    register_router(autonomy_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import legacy_envelope_adapter

    for prefix in ("autonomy", "system", "coordination"):
        register_response_adapter(prefix, legacy_envelope_adapter)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result
    register_flow_result("autonomy_decisions_list", result_key="autonomy_decisions_list_result")


def _register_health_check() -> None:
    from AINDY.platform_layer.registry import register_health_check

    register_health_check("autonomy", lambda: {"status": "ok"})

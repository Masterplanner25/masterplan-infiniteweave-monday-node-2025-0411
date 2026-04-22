"""Rippletrace domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_models()
    _register_routers()
    _register_response_adapters()
    _register_flow_strategy()
    _register_flow_results()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.rippletrace.models as rippletrace_models

    register_models(rippletrace_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(rippletrace_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.rippletrace.routes.rippletrace_router import router as rippletrace_router
    from apps.rippletrace.routes.legacy_surface_router import router as legacy_surface_router
    from AINDY.routes.db_verify_router import router as db_verify_router

    register_router(rippletrace_router)
    register_router(legacy_surface_router)
    register_router(db_verify_router, legacy_root=True)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from apps._adapters import raw_json_adapter

    for prefix in ("rippletrace", "legacy_surface", "observability", "db", "flow"):
        register_response_adapter(prefix, raw_json_adapter)


def _register_flow_strategy() -> None:
    from AINDY.platform_layer.registry import register_flow_strategy
    from apps.rippletrace.flow_strategy import register
    register(register_flow_strategy)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "flow_runs_list": "flow_runs_list_result",
        "flow_run_get": "flow_run_get_result",
        "flow_run_history": "flow_run_history_result",
        "flow_run_resume": "flow_run_resume_result",
        "flow_registry_get": "flow_registry_get_result",
        "observability_execution_graph": "observability_rippletrace_result",
        "observability_rippletrace": "observability_rippletrace_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

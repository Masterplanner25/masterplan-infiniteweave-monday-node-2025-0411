"""Search domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_models()
    _register_routers()
    _register_route_prefixes()
    _register_response_adapters()
    _register_agent_tools()
    _register_agent_capabilities()
    _register_capture_rules()
    _register_flow_results()
    _register_flow_plans()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.search.models as search_models

    register_models(search_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(search_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.search.routes.leadgen_router import router as leadgen_router
    from apps.search.routes.research_results_router import router as research_router
    from apps.search.routes.research_results_router import search_history_router
    from apps.search.routes.seo_routes import router as seo_router

    register_router(leadgen_router)
    register_router(research_router)
    register_router(search_history_router)
    register_router(seo_router)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix
    register_route_prefix("leadgen", "flow")


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from apps._adapters import raw_json_adapter

    register_response_adapter("leadgen", raw_json_adapter)
    register_response_adapter("seo", raw_json_adapter)


def _register_agent_tools() -> None:
    from apps.search.agents.tools import register as register_search_tools
    register_search_tools()


def _register_agent_capabilities() -> None:
    from apps.search.agents.capabilities import register as register_search_capabilities
    register_search_capabilities()


def _register_capture_rules() -> None:
    from AINDY.platform_layer.registry import register_memory_policy
    from apps.search.memory_policy import register as register_search_memory_policy
    register_search_memory_policy(register_memory_policy)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "leadgen_search": "search_results",
        "leadgen_list": "leadgen_list_result",
        "leadgen_preview_search": "leadgen_preview_search_result",
        "research_create": "research_create_result",
        "research_list": "research_list_result",
        "research_query": "research_query_result",
        "search_history_list": "search_history_list_result",
        "search_history_get": "search_history_get_result",
        "search_history_delete": "search_history_delete_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

    register_flow_result("leadgen_search", completion_event="leadgen_search")


def _register_flow_plans() -> None:
    from AINDY.platform_layer.registry import register_flow_plan

    register_flow_plan(
        "leadgen_search",
        {"steps": ["leadgen_validate", "leadgen_search", "leadgen_store"]},
    )

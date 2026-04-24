import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_ROUTE_MODULES = [
    "apps.analytics.routes.analytics_router",
    "apps.analytics.routes.main_router",
    "apps.authorship.routes.authorship_router",
    "apps.autonomy.routes.autonomy_router",
    "apps.bridge.routes.bridge_router",
    "apps.dashboard.routes.dashboard_router",
    "apps.dashboard.routes.health_dashboard_router",
    "apps.identity.routes.identity_router",
    "apps.masterplan.routes.masterplan_router",
    "apps.masterplan.routes.score_router",
    "apps.network_bridge.routes.network_bridge_router",
    "apps.rippletrace.routes.legacy_surface_router",
    "apps.rippletrace.routes.rippletrace_router",
    "apps.search.routes.seo_routes",
    "apps.social.routes.social_router",
]

# Routes here are explicitly exempt with a reason.
# Format: "router_module_path:handler_function_name": "reason"
EXEMPT_ROUTES = {
    "apps.analytics.routes.analytics_router:get_masterplan_analytics": "read_only",
    "apps.analytics.routes.analytics_router:get_masterplan_summary": "read_only",
    "apps.analytics.routes.main_router:get_results": "read_only",
    "apps.analytics.routes.main_router:get_masterplans": "read_only",
    "apps.authorship.routes.authorship_router:_execute_authorship": "infra",
    "apps.autonomy.routes.autonomy_router:get_recent_autonomy_decisions": "read_only",
    "apps.bridge.routes.bridge_router:search_nodes": "read_only",
    "apps.dashboard.routes.dashboard_router:get_system_overview": "read_only",
    "apps.dashboard.routes.health_dashboard_router:get_health_logs": "infra",
    "apps.identity.routes.identity_router:boot_identity": "read_only",
    "apps.identity.routes.identity_router:get_identity": "read_only",
    "apps.identity.routes.identity_router:get_identity_evolution": "read_only",
    "apps.identity.routes.identity_router:get_identity_context": "read_only",
    "apps.masterplan.routes.masterplan_router:list_masterplans": "read_only",
    "apps.masterplan.routes.masterplan_router:get_masterplan": "read_only",
    "apps.masterplan.routes.masterplan_router:get_masterplan_projection": "read_only",
    "apps.masterplan.routes.score_router:get_my_score": "read_only",
    "apps.masterplan.routes.score_router:get_score_history": "read_only",
    "apps.masterplan.routes.score_router:get_score_feedback": "read_only",
    "apps.network_bridge.routes.network_bridge_router:list_authors": "read_only",
    "apps.rippletrace.routes.legacy_surface_router:analyze_ripple": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:proofboard_dashboard": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:top_drop_points": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:ripple_deltas": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:emerging_drops_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:predict_drop_point_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:prediction_summary_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:recommend_drop_point": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:recommendations_summary_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:influence_graph_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:influence_chain_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:causal_graph_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:causal_chain_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:narrative_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:narrative_summary_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:strategies_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:strategy_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:strategy_match_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:playbooks_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:playbook_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:playbook_match_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:generate_content_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:generate_variations_view": "read_only_legacy",
    "apps.rippletrace.routes.legacy_surface_router:learning_stats_view": "read_only_legacy",
    "apps.rippletrace.routes.rippletrace_router:get_ripples": "read_only",
    "apps.rippletrace.routes.rippletrace_router:all_drop_points": "read_only",
    "apps.rippletrace.routes.rippletrace_router:all_pings": "read_only",
    "apps.rippletrace.routes.rippletrace_router:recent_ripples": "read_only",
    "apps.rippletrace.routes.rippletrace_router:get_trace_graph": "read_only",
    "apps.search.routes.seo_routes:_execute_seo": "infra",
    "apps.social.routes.social_router:get_profile": "read_only",
    "apps.social.routes.social_router:get_feed": "read_only",
    "apps.social.routes.social_router:get_social_analytics": "read_only",
}

GATE_FUNCTION_NAMES = {
    "require_execution_unit",
    "to_envelope",
    "flow_result_to_envelope",
    "agent_result_to_envelope",
}
MUTATING_METHODS = {"post", "put", "delete"}


def _module_to_path(module_path: str) -> Path:
    return REPO_ROOT.joinpath(*module_path.split(".")).with_suffix(".py")


def _called_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _route_methods(func_node: ast.AST) -> set[str]:
    methods: set[str] = set()
    for decorator in getattr(func_node, "decorator_list", []):
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        if isinstance(target, ast.Attribute) and target.attr in {
            "get",
            "post",
            "put",
            "delete",
            "patch",
        }:
            methods.add(target.attr)
    return methods


def _function_map(module_path: str) -> dict[str, dict]:
    source = _module_to_path(module_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions: dict[str, dict] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        functions[node.name] = {
            "node": node,
            "methods": _route_methods(node),
            "calls": {
                name
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                for name in [_called_name(child)]
                if name
            },
        }
    return functions


def _has_gate_call(functions: dict[str, dict], func_name: str, visiting: set[str] | None = None) -> bool:
    if func_name not in functions:
        return False
    visiting = visiting or set()
    if func_name in visiting:
        return False
    visiting.add(func_name)
    calls = functions[func_name]["calls"]
    if calls & GATE_FUNCTION_NAMES:
        return True
    for called_name in calls:
        if called_name in functions and _has_gate_call(functions, called_name, visiting):
            return True
    return False


def test_all_mutating_routes_have_execution_gate():
    missing: list[str] = []

    for module_path in TARGET_ROUTE_MODULES:
        functions = _function_map(module_path)
        for func_name, details in functions.items():
            methods = details["methods"]
            if not methods or not (methods & MUTATING_METHODS):
                continue
            route_key = f"{module_path}:{func_name}"
            if route_key in EXEMPT_ROUTES:
                continue
            if not _has_gate_call(functions, func_name):
                missing.append(
                    f"{route_key} methods={','.join(sorted(m.upper() for m in methods))}"
                )

    assert not missing, "Ungated mutating routes:\n" + "\n".join(sorted(missing))


def test_exempt_routes_are_still_read_only():
    for route_key, reason in EXEMPT_ROUTES.items():
        if reason not in {"read_only", "read_only_legacy", "infra"}:
            continue
        module_path, func_name = route_key.split(":", 1)
        functions = _function_map(module_path)
        assert func_name in functions, f"Missing exempt handler: {route_key}"
        methods = functions[func_name]["methods"]
        if reason.startswith("read_only") or reason == "infra":
            assert methods == {"get"} or not methods, (
                f"Exempt route must stay GET-only or non-route helper: {route_key} methods={methods}"
            )

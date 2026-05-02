"""Platform extension registry.

The platform owns registries, not application behavior. Applications register
routers, syscalls, jobs, flows, event handlers, capture rules, and agent tools
from their own bootstrap modules.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from AINDY.platform_layer.agent_plugin_contracts import CapabilityProviderBundle
from AINDY.platform_layer.registry_contracts import (
    validate_agent_event,
    validate_agent_planner_context,
    validate_agent_ranking_strategy,
    validate_agent_run_tools,
    validate_agent_tool,
    validate_capability_definition,
    validate_capability_names,
    validate_event_handler,
    validate_execution_adapter,
    validate_flow_plan,
    validate_flow_registration,
    validate_flow_result_registration,
    validate_flow_strategy,
    validate_job_handler,
    validate_memory_policy,
    validate_response_adapter,
    validate_restricted_tool,
    validate_route_guard,
    validate_route_prefix,
    validate_router,
    validate_scheduled_job_entry,
    validate_startup_hook,
    validate_symbol,
    validate_symbols,
    validate_syscall_handler,
    validate_trigger_evaluator,
)

logger = logging.getLogger(__name__)

Handler = Callable[..., Any]

_routers: list[Any] = []
_root_routers: list[Any] = []
_legacy_root_routers: list[Any] = []
_syscalls: dict[str, Handler] = {}
_jobs: dict[str, Handler] = {}
_flows: list[Handler] = []
_flow_result_keys: dict[str, str] = {}
_flow_result_extractors: dict[str, Handler] = {}
_flow_completion_events: dict[str, str] = {}
_flow_plans: dict[str, dict[str, Any]] = {}
_event_handlers: dict[str, list[Handler]] = defaultdict(list)
_event_types: set[str] = set()
_capture_rules: dict[str, Any] = {}
_memory_policies: dict[str, Any] = {}
_scheduled_jobs: dict[str, dict[str, Any]] = {}
_response_adapters: dict[str, Handler] = {}
_route_guards: dict[str, Handler] = {}
_execution_adapters: dict[str, Handler] = {}
_startup_hooks: list[Handler] = []
_agent_tools: dict[str, Any] = {}
_agent_planner_contexts: dict[str, Handler] = {}
_agent_run_tools: dict[str, Handler] = {}
_agent_completion_hooks: dict[str, list[Handler]] = defaultdict(list)
_agent_event_emitters: dict[str, list[Handler]] = defaultdict(list)
_agent_ranking_strategy: Handler | None = None
_trigger_evaluators: dict[str, Handler] = {}
_flow_strategies: dict[str, Handler] = {}
_capability_definitions: dict[str, dict[str, Any]] = {}
_capability_definition_providers: list[Handler] = []
_tool_capabilities: dict[str, list[str]] = {}
_agent_capabilities: dict[str, list[str]] = {}
_restricted_tools: set[str] = set()
_route_prefixes: dict[str, str] = {
    "flow": "flow",
    "memory": "flow",
    "nodus": "nodus",
    "platform": "job",
}
_required_flow_nodes: list[str] = []
_required_syscalls: list[str] = []
_symbols: dict[str, Any] = {}
_loaded_plugins: set[str] = set()
_registered_apps: list[str] = []
_bootstrap_dependencies: dict[str, list[str]] = {}
_core_domains: list[str] = []
_degraded_domains: list[str] = []
_health_checks: dict[str, Callable[[], dict[str, Any]]] = {}
_PLUGIN_PROFILE_ENV_VARS: tuple[str, ...] = ("AINDY_BOOT_PROFILE", "AINDY_PLUGIN_PROFILE")
_active_plugin_profile: str | None = None
_runtime_agent_defaults_loaded = False


def register_router(router: Any, *, root: bool = False, legacy_root: bool = False) -> Any:
    validate_router(router)
    if legacy_root:
        _legacy_root_routers.append(router)
    elif root:
        _root_routers.append(router)
    else:
        _routers.append(router)
    return router


def get_routers() -> list[Any]:
    return list(_routers)


def get_root_routers() -> list[Any]:
    return list(_root_routers)


def get_legacy_root_routers() -> list[Any]:
    return list(_legacy_root_routers)


def register_syscall(name: str, handler: Handler) -> Handler:
    validate_syscall_handler(name, handler)
    _syscalls[name] = handler
    return handler


def get_syscall(name: str) -> Handler | None:
    return _syscalls.get(name)


def iter_syscalls() -> Iterable[tuple[str, Handler]]:
    return tuple(_syscalls.items())


def register_job(name: str, handler: Handler) -> Handler:
    validate_job_handler(name, handler)
    _jobs[name] = handler
    return handler


def get_job(name: str) -> Handler | None:
    return _jobs.get(name)


def iter_jobs() -> Iterable[tuple[str, Handler]]:
    return tuple(_jobs.items())


def register_flow(register_fn: Handler) -> Handler:
    validate_flow_registration(getattr(register_fn, "__name__", "<anonymous>"), register_fn)
    if register_fn in _flows:
        return register_fn
    _flows.append(register_fn)
    return register_fn


def register_flows() -> None:
    for register_fn in tuple(_flows):
        register_fn()


def register_flow_result(
    flow_name: str,
    *,
    result_key: str | None = None,
    extractor: Handler | None = None,
    completion_event: str | None = None,
) -> None:
    validate_flow_result_registration(
        flow_name,
        result_key=result_key,
        extractor=extractor,
        completion_event=completion_event,
    )
    if result_key is not None:
        _flow_result_keys[flow_name] = result_key
    if extractor is not None:
        _flow_result_extractors[flow_name] = extractor
    if completion_event is not None:
        _flow_completion_events[flow_name] = completion_event


def get_flow_result_key(flow_name: str) -> str | None:
    return _flow_result_keys.get(flow_name)


def get_flow_result_extractor(flow_name: str) -> Handler | None:
    return _flow_result_extractors.get(flow_name)


def get_flow_completion_event(flow_name: str) -> str | None:
    return _flow_completion_events.get(flow_name)


def register_flow_plan(flow_name: str, plan: dict[str, Any]) -> None:
    validate_flow_plan(flow_name, plan)
    _flow_plans[flow_name] = plan


def get_flow_plan(flow_name: str) -> dict[str, Any] | None:
    return _flow_plans.get(flow_name)


def register_event_handler(event_type: str, handler: Handler) -> Handler:
    validate_event_handler(event_type, handler)
    register_event_type(event_type)
    _event_handlers[event_type].append(handler)
    return handler


def get_event_handlers(event_type: str) -> list[Handler]:
    return list(_event_handlers.get(event_type, ()))


def register_event_type(event_type: str) -> str:
    if not event_type or not event_type.strip():
        raise ValueError("event_type must be a non-empty string")
    _event_types.add(event_type)
    return event_type


def get_event_types() -> set[str]:
    return set(_event_types)


def emit_event(event_type: str, context: dict[str, Any] | None = None) -> list[Any]:
    """Dispatch a generic registry event to app-registered handlers."""
    load_plugins()
    payload = context or {}
    results: list[Any] = []
    handlers = tuple(_event_handlers.get(event_type, ())) + tuple(_event_handlers.get("*", ()))
    for handler in handlers:
        results.append(handler(payload))
    return results


def register_scheduled_job(
    job_id: str,
    handler: Handler,
    *,
    name: str | None = None,
    trigger: str = "interval",
    trigger_kwargs: dict[str, Any] | None = None,
    replace_existing: bool = True,
) -> Handler:
    validate_scheduled_job_entry(
        job_id,
        handler=handler,
        trigger=trigger,
        trigger_kwargs=trigger_kwargs,
    )
    _scheduled_jobs[job_id] = {
        "id": job_id,
        "handler": handler,
        "name": name or job_id,
        "trigger": trigger,
        "trigger_kwargs": dict(trigger_kwargs or {}),
        "replace_existing": replace_existing,
    }
    return handler


def get_scheduled_jobs() -> tuple[dict[str, Any], ...]:
    load_plugins()
    return tuple(dict(job) for job in _scheduled_jobs.values())


def register_response_adapter(route_prefix: str, handler: Handler) -> Handler:
    validate_response_adapter(route_prefix, handler)
    _response_adapters[route_prefix.rstrip(".")] = handler
    return handler


def get_response_adapter(route_prefix: str) -> Handler | None:
    load_plugins()
    return _response_adapters.get(route_prefix.rstrip("."))


def register_route_guard(route_prefix: str, handler: Handler) -> Handler:
    validate_route_guard(route_prefix, handler)
    _route_guards[route_prefix.rstrip(".")] = handler
    return handler


def get_route_guard(route_prefix: str) -> Handler | None:
    load_plugins()
    return _route_guards.get(route_prefix.rstrip("."))


def register_execution_adapter(entity_type: str, handler: Handler) -> Handler:
    validate_execution_adapter(entity_type, handler)
    _execution_adapters[entity_type.strip()] = handler
    return handler


def get_execution_adapter(entity_type: str) -> Handler | None:
    load_plugins()
    return _execution_adapters.get(entity_type.strip())


def register_startup_hook(handler: Handler) -> Handler:
    validate_startup_hook(handler)
    _startup_hooks.append(handler)
    return handler


def run_startup_hooks(context: dict[str, Any] | None = None) -> list[Any]:
    load_plugins()
    payload = context or {}
    results: list[Any] = []
    for handler in tuple(_startup_hooks):
        results.append(handler(payload))
    return results


def register_capture_rule(event_type: str, rule: Any) -> Any:
    return register_memory_policy(event_type, rule)


def get_capture_rule(event_type: str) -> Any | None:
    return get_memory_policy(event_type)


def get_capture_rules() -> dict[str, Any]:
    load_plugins()
    return dict(_capture_rules)


def register_memory_policy(event_type: str, policy: Any) -> Any:
    validate_memory_policy(event_type, policy)
    _memory_policies[event_type] = policy
    _capture_rules[event_type] = policy
    try:
        from AINDY.memory import memory_capture_engine

        if isinstance(policy, dict):
            memory_capture_engine.EVENT_SIGNIFICANCE[event_type] = policy.get(
                "base_score",
                policy.get("significance", 0.4),
            )
    except Exception:
        logger.debug("memory policy compatibility update skipped", exc_info=True)
    return policy


def get_memory_policy(event_type: str) -> Any | None:
    load_plugins()
    return _memory_policies.get(event_type)


def get_memory_significance_rule(event_type: str) -> float | None:
    policy = get_memory_policy(event_type)
    if not isinstance(policy, dict):
        return None
    value = policy.get("base_score", policy.get("significance"))
    return float(value) if value is not None else None


def register_agent_tool(name: str, tool: Any) -> Any:
    validate_agent_tool(name, tool)
    _agent_tools[name] = tool
    return tool


def get_agent_tool(name: str) -> Any | None:
    _ensure_runtime_agent_defaults()
    return _agent_tools.get(name)


def iter_agent_tools() -> Iterable[tuple[str, Any]]:
    _ensure_runtime_agent_defaults()
    return tuple(_agent_tools.items())


def register_planner_context_provider(run_type: str, handler: Handler) -> Handler:
    validate_agent_planner_context(run_type, handler)
    _agent_planner_contexts[run_type] = handler
    return handler


def get_planner_context(run_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_runtime_agent_defaults()
    handler = _agent_planner_contexts.get(run_type) or _agent_planner_contexts.get("default")
    if handler is None:
        return {}
    value = handler(context or {})
    return value if isinstance(value, dict) else {}


def register_agent_planner_context(run_type: str, handler: Handler) -> Handler:
    return register_planner_context_provider(run_type, handler)


def register_run_tool_provider(run_type: str, handler: Handler) -> Handler:
    validate_agent_run_tools(run_type, handler)
    _agent_run_tools[run_type] = handler
    return handler


def get_tools_for_run(run_type: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    _ensure_runtime_agent_defaults()
    handler = _agent_run_tools.get(run_type) or _agent_run_tools.get("default")
    if handler is None:
        return []
    value = handler(context or {})
    return value if isinstance(value, list) else []


def register_agent_run_tools(run_type: str, handler: Handler) -> Handler:
    return register_run_tool_provider(run_type, handler)


def register_agent_completion_hook(run_type: str, handler: Handler) -> Handler:
    validate_agent_event(f"agent.completion.{run_type}", handler)
    _agent_completion_hooks[run_type].append(handler)
    return handler


def run_agent_completion_hooks(run_type: str, context: dict[str, Any]) -> list[Any]:
    _ensure_runtime_agent_defaults()
    results: list[Any] = []
    handlers = tuple(_agent_completion_hooks.get(run_type, ())) + tuple(
        _agent_completion_hooks.get("default", ()) if run_type != "default" else ()
    )
    for handler in handlers:
        results.append(handler(context))
    return results


def register_agent_event(event_name: str, handler: Handler) -> Handler:
    validate_agent_event(event_name, handler)
    _agent_event_emitters[event_name].append(handler)
    return handler


def emit_agent_event(event_name: str, context: dict[str, Any]) -> list[Any]:
    results: list[Any] = []
    for handler in tuple(_agent_event_emitters.get(event_name, ())):
        results.append(handler(context))
    return results


def register_agent_ranking_strategy(handler: Handler) -> Handler:
    validate_agent_ranking_strategy(handler)
    global _agent_ranking_strategy
    _agent_ranking_strategy = handler
    return handler


def get_agent_ranking_strategy() -> Handler | None:
    load_plugins()
    return _agent_ranking_strategy


def register_trigger_evaluator(trigger_type: str, handler: Handler) -> Handler:
    validate_trigger_evaluator(trigger_type, handler)
    _trigger_evaluators[trigger_type] = handler
    return handler


def get_trigger_evaluator(trigger_type: str) -> Handler | None:
    _ensure_runtime_agent_defaults()
    load_plugins()
    return _trigger_evaluators.get(trigger_type) or _trigger_evaluators.get("default")


def register_flow_strategy(flow_type: str, handler: Handler) -> Handler:
    validate_flow_strategy(flow_type, handler)
    _flow_strategies[flow_type] = handler
    return handler


def get_flow_strategy(flow_type: str) -> Handler | None:
    load_plugins()
    return _flow_strategies.get(flow_type) or _flow_strategies.get("default")


def register_capability_definition(name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    validate_capability_definition(name, metadata)
    _capability_definitions[name] = dict(metadata)
    return _capability_definitions[name]


def register_capability_definition_provider(handler: Handler) -> Handler:
    if not callable(handler):
        raise ValueError("capability definition provider must be callable")
    if handler not in _capability_definition_providers:
        _capability_definition_providers.append(handler)
    return handler


def _apply_capability_provider_bundle(bundle: CapabilityProviderBundle | dict[str, Any]) -> None:
    if not isinstance(bundle, dict):
        raise ValueError("capability provider must return a dict bundle")

    for name, metadata in (bundle.get("definitions") or {}).items():
        register_capability_definition(name, metadata)
    for tool_name, capabilities in (bundle.get("tool_capabilities") or {}).items():
        register_tool_capabilities(tool_name, capabilities)
    for agent_id, capabilities in (bundle.get("agent_capabilities") or {}).items():
        register_agent_capabilities(agent_id, capabilities)
    for tool_name in (bundle.get("restricted_tools") or []):
        register_restricted_tool(tool_name)


def _load_capability_definition_providers() -> None:
    _ensure_runtime_agent_defaults()
    load_plugins()
    for provider in tuple(_capability_definition_providers):
        try:
            _apply_capability_provider_bundle(provider())
        except Exception as exc:
            logger.warning("Capability definition provider failed: %s", exc)


def _ensure_runtime_agent_defaults() -> None:
    global _runtime_agent_defaults_loaded
    if _runtime_agent_defaults_loaded:
        return
    from AINDY.platform_layer import runtime_agent_defaults

    runtime_agent_defaults.register()
    _runtime_agent_defaults_loaded = True


def get_capability_definition(name: str) -> dict[str, Any] | None:
    _load_capability_definition_providers()
    return _capability_definitions.get(name)


def get_capability_definitions() -> dict[str, dict[str, Any]]:
    _load_capability_definition_providers()
    return {name: dict(metadata) for name, metadata in _capability_definitions.items()}


def register_tool_capabilities(tool_name: str, capability_names: list[str]) -> list[str]:
    validate_capability_names("Tool capabilities", tool_name, capability_names)
    capabilities = sorted({name for name in capability_names if isinstance(name, str)})
    _tool_capabilities[tool_name] = capabilities
    return capabilities


def get_capabilities_for_tool(tool_name: str) -> list[str]:
    _load_capability_definition_providers()
    return list(_tool_capabilities.get(tool_name, ()))


def register_agent_capabilities(agent_id: str, capability_names: list[str]) -> list[str]:
    validate_capability_names("Agent capabilities", agent_id, capability_names)
    capabilities = sorted({name for name in capability_names if isinstance(name, str)})
    _agent_capabilities[agent_id] = capabilities
    return capabilities


def get_capabilities_for_agent(agent_id: str) -> list[str]:
    _load_capability_definition_providers()
    return list(_agent_capabilities.get(agent_id, ()))


def register_restricted_tool(tool_name: str) -> str:
    validate_restricted_tool(tool_name)
    _restricted_tools.add(tool_name)
    return tool_name


def get_restricted_tools() -> set[str]:
    _load_capability_definition_providers()
    return set(_restricted_tools)


def register_route_prefix(prefix: str, execution_unit_type: str) -> None:
    validate_route_prefix(prefix, execution_unit_type)
    _route_prefixes[prefix] = execution_unit_type


def get_route_prefix(prefix: str) -> str | None:
    return _route_prefixes.get(prefix)


def register_required_flow_node(node_name: str) -> str:
    """Register a flow node name that must exist after bootstrap."""
    if not node_name or not isinstance(node_name, str):
        raise ValueError(f"node_name must be a non-empty string, got {node_name!r}")
    _required_flow_nodes.append(node_name)
    return node_name


def get_required_flow_nodes() -> list[str]:
    return list(_required_flow_nodes)


def register_required_syscall(name: str) -> None:
    """Declare that a syscall must be present after bootstrap."""
    if not name or not isinstance(name, str):
        raise ValueError(f"name must be a non-empty string, got {name!r}")
    if name not in _required_syscalls:
        _required_syscalls.append(name)


def get_required_syscalls() -> list[str]:
    return list(_required_syscalls)


def register_symbol(name: str, value: Any) -> Any:
    validate_symbol(name)
    _symbols[name] = value
    return value


def get_symbol(name: str) -> Any | None:
    return _symbols.get(name)


def register_symbols(symbols: dict[str, Any]) -> None:
    validate_symbols(symbols)
    for name, value in symbols.items():
        if not name.startswith("__"):
            register_symbol(name, value)


def publish_degraded_domains(domains: Iterable[str]) -> list[str]:
    published: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        if not isinstance(domain, str):
            continue
        normalized = domain.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        published.append(normalized)

    global _degraded_domains
    _degraded_domains = published
    return list(_degraded_domains)


def get_degraded_domains() -> list[str]:
    return list(_degraded_domains)


def register_health_check(app_name: str, check_fn: Callable[[], dict[str, Any]]) -> Callable[[], dict[str, Any]]:
    if not isinstance(app_name, str) or not app_name.strip():
        raise ValueError("app_name must be a non-empty string")
    if not callable(check_fn):
        raise ValueError("check_fn must be callable")
    _health_checks[app_name.strip()] = check_fn
    return check_fn


def get_all_health_checks() -> dict[str, Callable[[], dict[str, Any]]]:
    return dict(_health_checks)


def publish_bootstrap_registration(app_name: str, dependencies: list[str] | None = None) -> str:
    normalized = str(app_name or "").strip()
    if not normalized:
        raise ValueError("app_name must be a non-empty string")
    if normalized not in _registered_apps:
        _registered_apps.append(normalized)
    _bootstrap_dependencies[normalized] = [
        str(dependency).strip()
        for dependency in (dependencies or [])
        if str(dependency).strip()
    ]
    return normalized


def publish_core_domains(domains: Iterable[str]) -> list[str]:
    published = sorted(
        {
            str(domain).strip()
            for domain in domains
            if isinstance(domain, str) and str(domain).strip()
        }
    )
    global _core_domains
    _core_domains = published
    return list(_core_domains)


def get_registered_apps() -> list[str]:
    return list(_registered_apps)


def get_bootstrap_dependencies() -> dict[str, list[str]]:
    return {name: list(deps) for name, deps in _bootstrap_dependencies.items()}


def get_core_domains() -> list[str]:
    load_plugins()
    return list(_core_domains)


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / "aindy_plugins.json"


def _read_plugin_manifest(manifest_path: str | Path | None = None) -> tuple[Path, dict[str, Any] | None]:
    path = Path(manifest_path) if manifest_path is not None else _default_manifest_path()
    if not path.exists():
        return path, None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Plugin manifest at {path} must be a JSON object")
    return path, data


def _normalize_plugin_profile_plugins(plugins: Any, *, profile_name: str, path: Path) -> list[str]:
    if plugins is None:
        return []
    if not isinstance(plugins, list):
        raise ValueError(
            f"Plugin profile {profile_name!r} in {path} must declare a list of plugins"
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for module_name in plugins:
        if not isinstance(module_name, str):
            raise ValueError(
                f"Plugin profile {profile_name!r} in {path} contains a non-string plugin entry"
            )
        cleaned = module_name.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _resolve_requested_plugin_profile(profile: str | None = None) -> str | None:
    if isinstance(profile, str) and profile.strip():
        return profile.strip()
    for env_name in _PLUGIN_PROFILE_ENV_VARS:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return None


def _plugin_boot_failure(
    *,
    path: Path,
    profile_name: str,
    module_name: str | None = None,
    reason: str,
) -> RuntimeError:
    module_detail = f" plugin module {module_name!r}" if module_name else ""
    return RuntimeError(
        f"Failed to boot plugin profile {profile_name!r} from {path}:{module_detail} {reason}. "
        "If you intend to start the runtime without app plugins, explicitly select "
        "the zero-plugin profile (for example `AINDY_BOOT_PROFILE=platform-only`)."
    )


def _resolve_plugin_profile_selection(
    manifest_path: str | Path | None = None,
    *,
    profile: str | None = None,
) -> tuple[str, list[str], bool]:
    path, data = _read_plugin_manifest(manifest_path)
    if data is None:
        return "missing", [], False

    requested_profile = _resolve_requested_plugin_profile(profile)
    legacy_plugins = data.get("plugins")
    if isinstance(legacy_plugins, list):
        return "__legacy__", _normalize_plugin_profile_plugins(
            legacy_plugins,
            profile_name="__legacy__",
            path=path,
        ), False

    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(
            f"Plugin manifest at {path} must declare either top-level 'plugins' or 'profiles'"
        )

    if requested_profile:
        selected_profile = requested_profile
        explicitly_selected = True
    else:
        explicitly_selected = False
        default_profile = data.get("default_profile")
        if isinstance(default_profile, str) and default_profile.strip():
            selected_profile = default_profile.strip()
        elif "default-apps" in profiles:
            selected_profile = "default-apps"
        elif len(profiles) == 1:
            selected_profile = next(iter(profiles))
        else:
            raise ValueError(
                f"Plugin manifest at {path} must declare 'default_profile' when multiple profiles exist"
            )

    if selected_profile not in profiles:
        raise ValueError(
            f"Plugin profile {selected_profile!r} not found in manifest {path}"
        )

    profile_entry = profiles[selected_profile]
    if not isinstance(profile_entry, dict):
        raise ValueError(
            f"Plugin profile {selected_profile!r} in {path} must be a JSON object"
        )

    return selected_profile, _normalize_plugin_profile_plugins(
        profile_entry.get("plugins"),
        profile_name=selected_profile,
        path=path,
    ), explicitly_selected


def resolve_plugin_profile(
    manifest_path: str | Path | None = None,
    *,
    profile: str | None = None,
) -> tuple[str, list[str]]:
    selected_profile, plugins, _explicitly_selected = _resolve_plugin_profile_selection(
        manifest_path,
        profile=profile,
    )
    return selected_profile, plugins


def get_active_plugin_profile(manifest_path: str | Path | None = None) -> str:
    global _active_plugin_profile
    if isinstance(_active_plugin_profile, str) and _active_plugin_profile.strip():
        return _active_plugin_profile
    profile_name, _plugin_modules = resolve_plugin_profile(manifest_path)
    _active_plugin_profile = profile_name
    return profile_name


def get_plugin_boot_order(
    manifest_path: str | Path | None = None,
    *,
    profile: str | None = None,
) -> list[str]:
    path = Path(manifest_path) if manifest_path is not None else _default_manifest_path()
    profile_name, plugin_modules, explicitly_selected = _resolve_plugin_profile_selection(
        manifest_path,
        profile=profile,
    )
    if not plugin_modules:
        if profile_name == "missing":
            return []
        if explicitly_selected:
            return []
        raise _plugin_boot_failure(
            path=path,
            profile_name=profile_name,
            reason="declares zero plugin modules",
        )

    boot_order: list[str] = []
    for module_name in plugin_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise _plugin_boot_failure(
                path=path,
                profile_name=profile_name,
                module_name=module_name,
                reason=f"could not be imported ({exc.__class__.__name__}: {exc})",
            ) from exc
        discover = getattr(module, "get_resolved_boot_order", None)
        if callable(discover):
            try:
                value = discover()
            except Exception as exc:
                raise _plugin_boot_failure(
                    path=path,
                    profile_name=profile_name,
                    module_name=module_name,
                    reason=f"failed during boot-order discovery ({exc.__class__.__name__}: {exc})",
                ) from exc
            if isinstance(value, list):
                boot_order.extend(name for name in value if isinstance(name, str) and name.strip())
                continue
        boot_order.append(module_name)
    return boot_order


def load_plugins(
    manifest_path: str | Path | None = None,
    *,
    profile: str | None = None,
) -> list[str]:
    """Load plugin bootstrap modules listed in the root manifest.

    The manifest keeps application module names outside AINDY source. Supported
    shapes are either the legacy ``{"plugins": [...]}`` list or the runtime-owned
    profile format:

    ``{"default_profile": "default-apps", "profiles": {"platform-only": {"plugins": []}, ...}}``
    """

    path, data = _read_plugin_manifest(manifest_path)
    if data is None:
        logger.info("No plugin manifest found at %s", path)
        return []

    global _active_plugin_profile
    active_profile, plugin_modules, explicitly_selected = _resolve_plugin_profile_selection(
        path,
        profile=profile,
    )
    _active_plugin_profile = active_profile
    if not plugin_modules:
        if not explicitly_selected:
            raise _plugin_boot_failure(
                path=path,
                profile_name=active_profile,
                reason="declares zero plugin modules",
            )
        logger.info(
            "Active plugin profile %s contains no plugin modules; runtime is starting without apps.",
            active_profile,
        )
        return []
    loaded: list[str] = []
    for module_name in plugin_modules:
        if module_name in _loaded_plugins:
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise _plugin_boot_failure(
                path=path,
                profile_name=active_profile,
                module_name=module_name,
                reason=f"could not be imported ({exc.__class__.__name__}: {exc})",
            ) from exc
        bootstrap = getattr(module, "bootstrap", None)
        if callable(bootstrap):
            try:
                bootstrap()
            except Exception as exc:
                raise _plugin_boot_failure(
                    path=path,
                    profile_name=active_profile,
                    module_name=module_name,
                    reason=f"bootstrap raised {exc.__class__.__name__}: {exc}",
                ) from exc
        _loaded_plugins.add(module_name)
        loaded.append(module_name)
    if loaded:
        logger.info(
            "Loaded platform plugins from profile %s: %s",
            active_profile,
            ", ".join(loaded),
        )
    return loaded

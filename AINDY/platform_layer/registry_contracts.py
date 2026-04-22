from __future__ import annotations

import inspect
from typing import Any, Protocol, TypedDict


class AgentToolContract(TypedDict):
    fn: Any
    risk: str
    description: str
    capability: str
    required_capability: str
    category: str
    egress_scope: str


class CapabilityDefinitionContract(TypedDict):
    description: str
    risk_level: str


class ScheduledJobContract(TypedDict):
    handler: Any
    trigger: str
    trigger_kwargs: dict[str, Any]


class ResumeContextProvider(Protocol):
    def __call__(self, context: dict[str, Any]) -> dict[str, Any]:
        ...


RISK_LEVELS = {"low", "medium", "high"}
AGENT_TOOL_KEYS = {
    "fn",
    "risk",
    "description",
    "capability",
    "required_capability",
    "category",
    "egress_scope",
}
ADAPTER_KWARGS = ("route_name", "canonical", "status_code", "trace_headers")
GUARD_KWARGS = ("request", "route_prefix", "user_context")


def _source_hint() -> str:
    stack = inspect.stack(context=0)
    try:
        if len(stack) >= 3:
            frame = stack[2]
            return f"{frame.filename}:{frame.lineno}"
        if len(stack) >= 2:
            frame = stack[1]
            return f"{frame.filename}:{frame.lineno}"
    finally:
        del stack
    return "<unknown>"


def _fail(kind: str, name: str, detail: str) -> None:
    raise ValueError(f"{kind} '{name}' registered by {_source_hint()} {detail}")


def _signature(handler: Any) -> inspect.Signature:
    try:
        return inspect.signature(handler)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not inspect callable signature: {exc}") from exc


def _signature_text(handler: Any) -> str:
    try:
        return str(_signature(handler))
    except ValueError:
        return "<uninspectable>"


def _is_required(parameter: inspect.Parameter) -> bool:
    return (
        parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and parameter.default is inspect._empty
    )


def _required_parameters(handler: Any) -> list[inspect.Parameter]:
    return [param for param in _signature(handler).parameters.values() if _is_required(param)]


def _has_varargs(handler: Any) -> bool:
    return any(
        param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for param in _signature(handler).parameters.values()
    )


def _validate_non_empty_string(value_name: str, value: Any, kind: str, registration_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(kind, registration_name, f"must use a non-empty string for {value_name}. Got: {value!r}")


def _validate_single_context_callable(
    *,
    kind: str,
    name: str,
    handler: Any,
    allowed_names: set[str],
) -> None:
    if not callable(handler):
        _fail(kind, name, f"must be callable. Got: {type(handler).__name__}")
    params = _required_parameters(handler)
    if _has_varargs(handler):
        return
    if len(params) != 1 or params[0].name not in allowed_names:
        _fail(
            kind,
            name,
            f"must accept a single {sorted(allowed_names)} parameter. Got: {_signature_text(handler)}",
        )


def _validate_noarg_callable(kind: str, name: str, handler: Any) -> None:
    if not callable(handler):
        _fail(kind, name, f"must be callable. Got: {type(handler).__name__}")
    if _has_varargs(handler):
        return
    params = _required_parameters(handler)
    if params:
        _fail(kind, name, f"must accept no required parameters. Got: {_signature_text(handler)}")


def _validate_named_kwargs_callable(
    *,
    kind: str,
    name: str,
    handler: Any,
    required_names: tuple[str, ...],
) -> None:
    if not callable(handler):
        _fail(kind, name, f"must be callable. Got: {type(handler).__name__}")
    sig = _signature(handler)
    params = sig.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
        return
    missing = [param for param in required_names if param not in params]
    required = _required_parameters(handler)
    extra_required = [param.name for param in required if param.name not in required_names]
    if missing or extra_required:
        detail = []
        if missing:
            detail.append(f"missing keyword parameters {missing}")
        if extra_required:
            detail.append(f"has unrelated required parameters {extra_required}")
        _fail(kind, name, f"must accept keyword args {list(required_names)}; {'; '.join(detail)}. Got: {sig}")


def validate_router(router: Any) -> None:
    if router is None or not hasattr(router, "routes"):
        raise ValueError(
            f"Router registration at {_source_hint()} must provide a FastAPI/APIRouter-like object with a 'routes' attribute. "
            f"Got: {type(router).__name__}"
        )


def validate_syscall_handler(name: str, handler: Any) -> None:
    _validate_non_empty_string("name", name, "Syscall handler", name or "<unnamed>")
    _validate_single_context_callable(
        kind="Syscall handler",
        name=name,
        handler=handler,
        allowed_names={"context", "payload"},
    )


def validate_job_handler(name: str, handler: Any) -> None:
    _validate_non_empty_string("name", name, "Job handler", name or "<unnamed>")
    if not callable(handler):
        _fail("Job handler", name, f"must be callable. Got: {type(handler).__name__}")
    if _has_varargs(handler):
        return
    sig = _signature(handler)
    params = _required_parameters(handler)
    if any(param.kind == inspect.Parameter.POSITIONAL_ONLY for param in sig.parameters.values()):
        _fail("Job handler", name, f"must not use positional-only parameters. Got: {_signature_text(handler)}")
    if not params:
        return
    positional_required = [
        param for param in params
        if param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    keyword_only_required = [
        param for param in params
        if param.kind == inspect.Parameter.KEYWORD_ONLY
    ]
    if len(positional_required) == 1 and positional_required[0].name in {"payload", "context"}:
        return
    if (
        len(positional_required) == 2
        and positional_required[0].name in {"payload", "context"}
        and positional_required[1].name == "db"
    ):
        return
    if not positional_required and keyword_only_required:
        return
    _fail(
        "Job handler",
        name,
        "must accept one of: (), (payload), (context), (payload, db), (context, db), keyword-only required parameters, "
        "or flexible *args/**kwargs. "
        f"Got: {_signature_text(handler)}",
    )


def validate_flow_registration(name: str, handler: Any) -> None:
    _validate_non_empty_string("name", name, "Flow registration", name or "<unnamed>")
    _validate_noarg_callable("Flow registration", name, handler)


def validate_flow_result_registration(
    flow_name: str,
    *,
    result_key: Any,
    extractor: Any,
    completion_event: Any,
) -> None:
    _validate_non_empty_string("flow_name", flow_name, "Flow result registration", flow_name or "<unnamed>")
    if result_key is None and extractor is None and completion_event is None:
        _fail("Flow result registration", flow_name, "must provide at least one of result_key, extractor, or completion_event.")
    if result_key is not None and (not isinstance(result_key, str) or not result_key.strip()):
        _fail("Flow result registration", flow_name, f"must use a non-empty string for result_key. Got: {result_key!r}")
    if completion_event is not None and (not isinstance(completion_event, str) or not completion_event.strip()):
        _fail(
            "Flow result registration",
            flow_name,
            f"must use a non-empty string for completion_event. Got: {completion_event!r}",
        )
    if extractor is not None:
        _validate_single_context_callable(
            kind="Flow result extractor",
            name=flow_name,
            handler=extractor,
            allowed_names={"state", "context", "payload"},
        )


def validate_flow_plan(flow_name: str, plan: Any) -> None:
    _validate_non_empty_string("flow_name", flow_name, "Flow plan", flow_name or "<unnamed>")
    if not isinstance(plan, dict):
        _fail("Flow plan", flow_name, f"must be a dict. Got: {type(plan).__name__}")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not all(isinstance(step, str) and step.strip() for step in steps):
        _fail("Flow plan", flow_name, f"must include a 'steps' list[str]. Got: {plan!r}")


def validate_event_handler(event_type: str, handler: Any) -> None:
    _validate_non_empty_string("event_type", event_type, "Event handler", event_type or "<unnamed>")
    _validate_single_context_callable(
        kind="Event handler",
        name=event_type,
        handler=handler,
        allowed_names={"context", "payload"},
    )


def validate_scheduled_job_entry(
    job_id: str,
    *,
    handler: Any,
    trigger: Any,
    trigger_kwargs: Any,
) -> None:
    _validate_non_empty_string("job_id", job_id, "Scheduled job", job_id or "<unnamed>")
    validate_job_handler(job_id, handler)
    if not isinstance(trigger, str) or not trigger.strip():
        _fail("Scheduled job", job_id, f"must use a non-empty string trigger. Got: {trigger!r}")
    if trigger_kwargs is not None and not isinstance(trigger_kwargs, dict):
        _fail("Scheduled job", job_id, f"must use a dict for trigger_kwargs. Got: {type(trigger_kwargs).__name__}")


def validate_response_adapter(route_prefix: str, handler: Any) -> None:
    _validate_non_empty_string("route_prefix", route_prefix, "Response adapter", route_prefix or "<unnamed>")
    _validate_named_kwargs_callable(
        kind="Response adapter",
        name=route_prefix,
        handler=handler,
        required_names=ADAPTER_KWARGS,
    )


def validate_route_guard(route_prefix: str, handler: Any) -> None:
    _validate_non_empty_string("route_prefix", route_prefix, "Route guard", route_prefix or "<unnamed>")
    _validate_named_kwargs_callable(
        kind="Route guard",
        name=route_prefix,
        handler=handler,
        required_names=GUARD_KWARGS,
    )


def validate_execution_adapter(entity_type: str, handler: Any) -> None:
    _validate_non_empty_string("entity_type", entity_type, "Execution adapter", entity_type or "<unnamed>")
    if not callable(handler):
        _fail("Execution adapter", entity_type, f"must be callable. Got: {type(handler).__name__}")
    if _has_varargs(handler):
        return
    params = _required_parameters(handler)
    if len(params) != 1:
        _fail("Execution adapter", entity_type, f"must accept exactly one entity parameter. Got: {_signature_text(handler)}")


def validate_startup_hook(handler: Any) -> None:
    _validate_single_context_callable(
        kind="Startup hook",
        name=getattr(handler, "__name__", "<anonymous>"),
        handler=handler,
        allowed_names={"context"},
    )


def validate_memory_policy(event_type: str, policy: Any) -> None:
    _validate_non_empty_string("event_type", event_type, "Memory policy", event_type or "<unnamed>")
    if not isinstance(policy, dict):
        _fail("Memory policy", event_type, f"must be a dict. Got: {type(policy).__name__}")
    if "node_type" not in policy or not isinstance(policy.get("node_type"), str) or not policy.get("node_type"):
        _fail("Memory policy", event_type, f"must include non-empty string key 'node_type'. Got: {policy!r}")
    if policy.get("significance") is None and policy.get("base_score") is None:
        _fail("Memory policy", event_type, f"must include 'significance' or 'base_score'. Got: {policy!r}")


def validate_agent_tool(name: str, tool: Any) -> None:
    _validate_non_empty_string("name", name, "Agent tool", name or "<unnamed>")
    if not isinstance(tool, dict):
        _fail("Agent tool", name, f"must be a dict. Got: {type(tool).__name__}")
    missing = sorted(AGENT_TOOL_KEYS - set(tool.keys()))
    if missing:
        _fail("Agent tool", name, f"is missing required keys {missing}. Got keys: {sorted(tool.keys())}")
    if not callable(tool.get("fn")):
        _fail("Agent tool", name, f"must provide callable 'fn'. Got: {type(tool.get('fn')).__name__}")
    risk = tool.get("risk")
    if risk not in RISK_LEVELS:
        _fail("Agent tool", name, f"must use risk in {sorted(RISK_LEVELS)}. Got: {risk!r}")


def validate_agent_planner_context(run_type: str, handler: Any) -> None:
    _validate_non_empty_string("run_type", run_type, "Agent planner context", run_type or "<unnamed>")
    _validate_single_context_callable(
        kind="Agent planner context",
        name=run_type,
        handler=handler,
        allowed_names={"context", "_context"},
    )


def validate_agent_run_tools(run_type: str, handler: Any) -> None:
    _validate_non_empty_string("run_type", run_type, "Agent run tools", run_type or "<unnamed>")
    _validate_single_context_callable(
        kind="Agent run tools",
        name=run_type,
        handler=handler,
        allowed_names={"context", "_context"},
    )


def validate_agent_event(event_name: str, handler: Any) -> None:
    _validate_non_empty_string("event_name", event_name, "Agent event handler", event_name or "<unnamed>")
    _validate_single_context_callable(
        kind="Agent event handler",
        name=event_name,
        handler=handler,
        allowed_names={"context", "payload"},
    )


def validate_agent_ranking_strategy(handler: Any) -> None:
    name = getattr(handler, "__name__", "<anonymous>")
    if not callable(handler):
        _fail("Agent ranking strategy", name, f"must be callable. Got: {type(handler).__name__}")
    if _has_varargs(handler):
        return
    params = _required_parameters(handler)
    if len(params) != 2 or [param.name for param in params] != ["candidates", "context"]:
        _fail(
            "Agent ranking strategy",
            name,
            f"must accept (candidates, context). Got: {_signature_text(handler)}",
        )


def validate_trigger_evaluator(trigger_type: str, handler: Any) -> None:
    _validate_non_empty_string("trigger_type", trigger_type, "Trigger evaluator", trigger_type or "<unnamed>")
    _validate_single_context_callable(
        kind="Trigger evaluator",
        name=trigger_type,
        handler=handler,
        allowed_names={"payload", "context"},
    )


def validate_flow_strategy(flow_type: str, handler: Any) -> None:
    _validate_non_empty_string("flow_type", flow_type, "Flow strategy", flow_type or "<unnamed>")
    _validate_single_context_callable(
        kind="Flow strategy",
        name=flow_type,
        handler=handler,
        allowed_names={"context", "payload"},
    )


def validate_capability_definition(name: str, metadata: Any) -> None:
    _validate_non_empty_string("name", name, "Capability definition", name or "<unnamed>")
    if not isinstance(metadata, dict):
        _fail("Capability definition", name, f"must be a dict. Got: {type(metadata).__name__}")
    missing = [key for key in ("description", "risk_level") if key not in metadata]
    if missing:
        _fail("Capability definition", name, f"is missing required keys {missing}. Got: {metadata!r}")
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        _fail("Capability definition", name, f"must include non-empty string description. Got: {metadata!r}")
    if metadata.get("risk_level") not in RISK_LEVELS:
        _fail(
            "Capability definition",
            name,
            f"must use risk_level in {sorted(RISK_LEVELS)}. Got: {metadata.get('risk_level')!r}",
        )


def validate_capability_names(registration_kind: str, owner_name: str, capability_names: Any) -> None:
    if not isinstance(capability_names, list):
        _fail(registration_kind, owner_name, f"must be a list[str]. Got: {type(capability_names).__name__}")
    if not capability_names:
        _fail(registration_kind, owner_name, "must include at least one capability name.")
    if not all(isinstance(name, str) and name.strip() for name in capability_names):
        _fail(registration_kind, owner_name, f"must contain only non-empty strings. Got: {capability_names!r}")


def validate_restricted_tool(tool_name: Any) -> None:
    _validate_non_empty_string("tool_name", tool_name, "Restricted tool", str(tool_name or "<unnamed>"))


def validate_route_prefix(prefix: Any, execution_unit_type: Any) -> None:
    _validate_non_empty_string("prefix", prefix, "Route prefix", str(prefix or "<unnamed>"))
    _validate_non_empty_string(
        "execution_unit_type",
        execution_unit_type,
        "Route prefix",
        str(prefix or "<unnamed>"),
    )


def validate_symbol(name: Any) -> None:
    _validate_non_empty_string("name", name, "Symbol", str(name or "<unnamed>"))


def validate_symbols(symbols: Any) -> None:
    if not isinstance(symbols, dict):
        raise ValueError(
            f"Symbol collection registered by {_source_hint()} must be a dict[str, Any]. Got: {type(symbols).__name__}"
        )
    invalid = [name for name in symbols.keys() if not isinstance(name, str) or not name.strip()]
    if invalid:
        raise ValueError(
            f"Symbol collection registered by {_source_hint()} must use non-empty string keys. Got invalid keys: {invalid!r}"
        )

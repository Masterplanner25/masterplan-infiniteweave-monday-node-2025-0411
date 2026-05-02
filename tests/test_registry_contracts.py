from __future__ import annotations

import logging

import pytest

import apps.bootstrap as apps_bootstrap
from AINDY.platform_layer import registry


def _valid_agent_tool(fn):
    return {
        "fn": fn,
        "risk": "low",
        "description": "tool description",
        "capability": "tool:test",
        "required_capability": "execute_flow",
        "category": "testing",
        "egress_scope": "internal",
    }


def _valid_capability(risk_level: str = "low") -> dict[str, str]:
    return {"description": "capability description", "risk_level": risk_level}


def _response_adapter_one(*, route_name, canonical, status_code, trace_headers):
    return canonical


def _response_adapter_two(*, route_name, canonical, status_code, trace_headers):
    return trace_headers


def _route_guard_one(*, request, route_prefix, user_context):
    return True


def _route_guard_two(**kwargs):
    return kwargs.get("route_prefix")


def _execution_adapter_one(entity):
    return {"id": getattr(entity, "id", None)}


def _execution_adapter_two(item):
    return {"item": item}


def _event_handler_one(context: dict):
    return None


def _event_handler_two(payload: dict):
    return payload


def _startup_hook_one(context: dict):
    return None


def _startup_hook_two(context: dict):
    return context.get("source")


def _planner_context_one(context: dict):
    return {"system_prompt": "ok"}


def _planner_context_two(_context: dict):
    return {"context_block": "ok"}


def _run_tools_one(context: dict):
    return [{"name": "tool.one"}]


def _run_tools_two(_context: dict):
    return [{"name": "tool.two"}]


def _agent_event_one(context: dict):
    return None


def _agent_event_two(payload: dict):
    return payload


def _ranking_one(candidates, context):
    return candidates


def _ranking_two(candidates, context):
    return list(reversed(candidates))


def _trigger_one(payload: dict):
    return {"decision": "execute", "priority": 1.0, "reason": "ok"}


def _trigger_two(context: dict):
    return {"decision": "defer", "priority": 0.0, "reason": "wait"}


def _flow_strategy_one(context: dict):
    return {"flow_type": "default"}


def _flow_strategy_two(payload: dict):
    return {"flow_type": payload.get("type")}


def _syscall_one(context: dict):
    return {"ok": True}


def _syscall_two(payload: dict):
    return {"echo": payload}


def _job_zero():
    return None


def _job_payload(payload):
    return payload


def _job_payload_db(payload, db):
    return db


def _job_varargs(*args, **kwargs):
    return kwargs or args


def _flow_register_one():
    return None


def _flow_register_two():
    return "registered"


def _flow_result_extractor_one(state):
    return {"result": state}


def _flow_result_extractor_two(context):
    return {"result": context}


@pytest.mark.parametrize(
    ("register_call", "description"),
    [
        (lambda: registry.register_syscall("syscall.valid.one", _syscall_one), "syscall handler 1"),
        (lambda: registry.register_syscall("syscall.valid.two", _syscall_two), "syscall handler 2"),
        (lambda: registry.register_job("job.valid.zero", _job_zero), "job handler 1"),
        (lambda: registry.register_job("job.valid.payload", _job_payload), "job handler 2"),
        (lambda: registry.register_event_handler("event.valid.one", _event_handler_one), "event handler 1"),
        (lambda: registry.register_event_handler("event.valid.two", _event_handler_two), "event handler 2"),
        (lambda: registry.register_flow(_flow_register_one), "flow registration 1"),
        (lambda: registry.register_flow(_flow_register_two), "flow registration 2"),
        (lambda: registry.register_agent_tool("tool.valid.one", _valid_agent_tool(_syscall_one)), "agent tool 1"),
        (lambda: registry.register_agent_tool("tool.valid.two", _valid_agent_tool(_syscall_two)), "agent tool 2"),
        (lambda: registry.register_capability_definition("cap.valid.one", _valid_capability("low")), "capability 1"),
        (lambda: registry.register_capability_definition("cap.valid.two", _valid_capability("high")), "capability 2"),
        (
            lambda: registry.register_scheduled_job(
                "sched.valid.one",
                _job_zero,
                trigger="interval",
                trigger_kwargs={"seconds": 30},
            ),
            "scheduled job 1",
        ),
        (
            lambda: registry.register_scheduled_job(
                "sched.valid.two",
                _job_payload_db,
                trigger="cron",
                trigger_kwargs={"hour": 7},
            ),
            "scheduled job 2",
        ),
        (lambda: registry.register_response_adapter("adapter.valid.one", _response_adapter_one), "response adapter 1"),
        (lambda: registry.register_response_adapter("adapter.valid.two", _response_adapter_two), "response adapter 2"),
        (lambda: registry.register_execution_adapter("entity.valid.one", _execution_adapter_one), "execution adapter 1"),
        (lambda: registry.register_execution_adapter("entity.valid.two", _execution_adapter_two), "execution adapter 2"),
        (lambda: registry.register_route_guard("guard.valid.one", _route_guard_one), "route guard 1"),
        (lambda: registry.register_route_guard("guard.valid.two", _route_guard_two), "route guard 2"),
        (lambda: registry.register_startup_hook(_startup_hook_one), "startup hook 1"),
        (lambda: registry.register_startup_hook(_startup_hook_two), "startup hook 2"),
        (lambda: registry.register_flow_result("flow.result.valid.one", result_key="flow_result"), "flow result 1"),
        (lambda: registry.register_flow_result("flow.result.valid.two", extractor=_flow_result_extractor_one), "flow result 2"),
        (lambda: registry.register_flow_plan("flow.plan.valid.one", {"steps": ["a", "b"]}), "flow plan 1"),
        (lambda: registry.register_flow_plan("flow.plan.valid.two", {"steps": ["x"]}), "flow plan 2"),
        (lambda: registry.register_memory_policy("memory.valid.one", {"significance": 0.5, "node_type": "outcome"}), "memory policy 1"),
        (lambda: registry.register_memory_policy("memory.valid.two", {"base_score": 0.7, "node_type": "insight"}), "memory policy 2"),
        (lambda: registry.register_agent_planner_context("planner.valid.one", _planner_context_one), "planner context 1"),
        (lambda: registry.register_agent_planner_context("planner.valid.two", _planner_context_two), "planner context 2"),
        (lambda: registry.register_agent_run_tools("run.tools.valid.one", _run_tools_one), "run tools 1"),
        (lambda: registry.register_agent_run_tools("run.tools.valid.two", _run_tools_two), "run tools 2"),
        (lambda: registry.register_agent_event("agent.event.valid.one", _agent_event_one), "agent event 1"),
        (lambda: registry.register_agent_event("agent.event.valid.two", _agent_event_two), "agent event 2"),
        (lambda: registry.register_agent_ranking_strategy(_ranking_one), "ranking strategy 1"),
        (lambda: registry.register_agent_ranking_strategy(_ranking_two), "ranking strategy 2"),
        (lambda: registry.register_trigger_evaluator("trigger.valid.one", _trigger_one), "trigger evaluator 1"),
        (lambda: registry.register_trigger_evaluator("trigger.valid.two", _trigger_two), "trigger evaluator 2"),
        (lambda: registry.register_flow_strategy("strategy.valid.one", _flow_strategy_one), "flow strategy 1"),
        (lambda: registry.register_flow_strategy("strategy.valid.two", _flow_strategy_two), "flow strategy 2"),
        (lambda: registry.register_tool_capabilities("tool.cap.valid", ["execute_flow"]), "tool capabilities"),
        (lambda: registry.register_agent_capabilities("agent.cap.valid", ["execute_flow"]), "agent capabilities"),
    ],
)
def test_valid_registrations_are_accepted(register_call, description):
    register_call()


@pytest.mark.parametrize(
    ("register_call", "message_fragment"),
    [
        (lambda: registry.register_syscall("syscall.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_syscall("syscall.bad.signature", lambda user_id, data: {}), "single"),
        (lambda: registry.register_syscall("", _syscall_one), "non-empty string"),
        (lambda: registry.register_job("job.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_job("job.bad.signature", lambda user_id: None), "must accept one of"),
        (lambda: registry.register_job("", _job_zero), "non-empty string"),
        (lambda: registry.register_event_handler("event.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_event_handler("event.bad.signature", lambda user_id, data: None), "single"),
        (lambda: registry.register_event_handler("", _event_handler_one), "non-empty string"),
        (lambda: registry.register_flow("not-a-callable"), "must be callable"),
        (lambda: registry.register_flow(lambda payload: None), "no required parameters"),
        (lambda: registry.register_flow_result("flow.result.bad.none"), "at least one"),
        (lambda: registry.register_flow_result("flow.result.bad.key", result_key=123), "result_key"),
        (lambda: registry.register_flow_result("flow.result.bad.extractor", extractor=lambda user_id, state: {}), "single"),
        (lambda: registry.register_flow_plan("flow.plan.bad.type", ["a", "b"]), "must be a dict"),
        (lambda: registry.register_flow_plan("flow.plan.bad.steps", {"steps": "not-a-list"}), "steps"),
        (lambda: registry.register_flow_plan("", {"steps": ["a"]}), "non-empty string"),
        (lambda: registry.register_agent_tool("tool.bad.type", "not-a-dict"), "must be a dict"),
        (lambda: registry.register_agent_tool("tool.bad.keys", {"fn": _syscall_one}), "missing required keys"),
        (lambda: registry.register_agent_tool("tool.bad.risk", {**_valid_agent_tool(_syscall_one), "risk": "severe"}), "must use risk"),
        (lambda: registry.register_capability_definition("cap.bad.type", "not-a-dict"), "must be a dict"),
        (lambda: registry.register_capability_definition("cap.bad.keys", {"description": "x"}), "missing required keys"),
        (lambda: registry.register_capability_definition("cap.bad.risk", {"description": "x", "risk_level": "severe"}), "risk_level"),
        (
            lambda: registry.register_scheduled_job("sched.bad.type", "not-a-callable", trigger="interval", trigger_kwargs={}),
            "must be callable",
        ),
        (
            lambda: registry.register_scheduled_job("sched.bad.trigger", _job_zero, trigger=123, trigger_kwargs={}),
            "trigger",
        ),
        (
            lambda: registry.register_scheduled_job("sched.bad.kwargs", _job_zero, trigger="interval", trigger_kwargs="bad"),
            "trigger_kwargs",
        ),
        (lambda: registry.register_response_adapter("adapter.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_response_adapter("adapter.bad.signature", lambda result: result), "keyword args"),
        (lambda: registry.register_response_adapter("", _response_adapter_one), "non-empty string"),
        (lambda: registry.register_execution_adapter("entity.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_execution_adapter("entity.bad.signature", lambda left, right: {}), "exactly one entity"),
        (lambda: registry.register_execution_adapter("", _execution_adapter_one), "non-empty string"),
        (lambda: registry.register_route_guard("guard.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_route_guard("guard.bad.signature", lambda request: True), "keyword args"),
        (lambda: registry.register_route_guard("", _route_guard_one), "non-empty string"),
        (lambda: registry.register_startup_hook("not-a-callable"), "must be callable"),
        (lambda: registry.register_startup_hook(lambda payload, extra: None), "single"),
        (lambda: registry.register_memory_policy("memory.bad.type", "not-a-dict"), "must be a dict"),
        (lambda: registry.register_memory_policy("memory.bad.node", {"significance": 0.5}), "node_type"),
        (lambda: registry.register_memory_policy("memory.bad.score", {"node_type": "outcome"}), "significance"),
        (lambda: registry.register_agent_planner_context("planner.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_agent_planner_context("planner.bad.signature", lambda user_id, db: {}), "single"),
        (lambda: registry.register_agent_run_tools("run.tools.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_agent_run_tools("run.tools.bad.signature", lambda user_id, db: []), "single"),
        (lambda: registry.register_agent_event("agent.event.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_agent_event("agent.event.bad.signature", lambda user_id, db: None), "single"),
        (lambda: registry.register_agent_ranking_strategy("not-a-callable"), "must be callable"),
        (lambda: registry.register_agent_ranking_strategy(lambda context: []), "candidates, context"),
        (lambda: registry.register_agent_ranking_strategy(lambda left, right, third: []), "candidates, context"),
        (lambda: registry.register_trigger_evaluator("trigger.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_trigger_evaluator("trigger.bad.signature", lambda user_id, db: {}), "single"),
        (lambda: registry.register_flow_strategy("strategy.bad.type", "not-a-callable"), "must be callable"),
        (lambda: registry.register_flow_strategy("strategy.bad.signature", lambda user_id, db: {}), "single"),
        (lambda: registry.register_tool_capabilities("tool.cap.bad.type", "not-a-list"), "list[str]"),
        (lambda: registry.register_tool_capabilities("tool.cap.bad.empty", []), "at least one capability"),
        (lambda: registry.register_tool_capabilities("tool.cap.bad.values", ["ok", ""]), "non-empty strings"),
        (lambda: registry.register_agent_capabilities("agent.cap.bad.type", "not-a-list"), "list[str]"),
        (lambda: registry.register_agent_capabilities("agent.cap.bad.empty", []), "at least one capability"),
        (lambda: registry.register_agent_capabilities("agent.cap.bad.values", ["ok", ""]), "non-empty strings"),
    ],
)
def test_invalid_registrations_raise_value_error(register_call, message_fragment):
    with pytest.raises(ValueError) as exc_info:
        register_call()
    assert message_fragment in str(exc_info.value)


def test_job_handler_varargs_registration_is_accepted():
    registry.register_job("job.valid.varargs", _job_varargs)


def test_flow_result_completion_event_registration_is_accepted():
    registry.register_flow_result("flow.result.valid.completion", completion_event="flow.completed")


def test_flow_registration_is_idempotent_for_same_callable():
    def _unique_flow_registration():
        return None

    before = len(registry._flows)

    registry.register_flow(_unique_flow_registration)
    registry.register_flow(_unique_flow_registration)

    after = len(registry._flows)
    assert after == before + 1


def test_startup_fails_fast_on_invalid_bootstrap(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(apps_bootstrap, "_BOOTSTRAPPED", False)
    monkeypatch.setattr(apps_bootstrap, "_DEGRADED_DOMAINS", [])

    import apps.tasks.bootstrap as tasks_bootstrap

    def _bad_register():
        raise ValueError("Job handler 'tasks.background.start' must be callable")

    monkeypatch.setattr(tasks_bootstrap, "register", _bad_register)

    with pytest.raises(RuntimeError) as exc_info:
        apps_bootstrap.bootstrap()

    assert "Core domain bootstrap failed for tasks" in str(exc_info.value)
    assert "tasks.background.start" in str(exc_info.value)
    assert "tasks" in caplog.text

    monkeypatch.setattr(apps_bootstrap, "_BOOTSTRAPPED", False)
    monkeypatch.setattr(apps_bootstrap, "_DEGRADED_DOMAINS", [])

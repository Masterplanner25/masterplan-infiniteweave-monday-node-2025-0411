from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


class _FakeQuery:
    def limit(self, _value):
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.executed = []

    def query(self, *_args, **_kwargs):
        return _FakeQuery()

    def execute(self, statement, *_args, **_kwargs):
        self.executed.append(statement)
        return []

    def close(self):
        self.closed = True


@pytest.fixture
def fake_sessionlocal():
    session = _FakeSession()

    def _factory():
        return session

    return session, _factory


def test_freelance_health_check_happy_path(monkeypatch, fake_sessionlocal):
    module = importlib.import_module("apps.freelance.bootstrap")
    session, factory = fake_sessionlocal

    monkeypatch.setattr("AINDY.db.database.SessionLocal", factory)
    monkeypatch.setattr("AINDY.config.settings.STRIPE_SECRET_KEY", "sk_test_" + ("x" * 32))

    assert module.freelance_health_check() is True
    assert session.closed is True


def test_freelance_health_check_raises_without_stripe_key(monkeypatch):
    module = importlib.import_module("apps.freelance.bootstrap")

    monkeypatch.setattr("AINDY.config.settings.STRIPE_SECRET_KEY", "")

    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY not configured"):
        module.freelance_health_check()


def test_masterplan_health_check_happy_path(monkeypatch, fake_sessionlocal):
    module = importlib.import_module("apps.masterplan.bootstrap")
    session, factory = fake_sessionlocal
    fake_cb = SimpleNamespace(state="closed", opened_at=None)
    circuit_breaker = importlib.import_module("AINDY.kernel.circuit_breaker")
    fake_cb.state = circuit_breaker.CircuitState.CLOSED

    monkeypatch.setattr("AINDY.db.database.SessionLocal", factory)
    monkeypatch.setattr("AINDY.kernel.circuit_breaker.get_openai_circuit_breaker", lambda: fake_cb)

    assert module.masterplan_health_check() is True
    assert session.closed is True


def test_masterplan_health_check_raises_when_circuit_open(monkeypatch):
    module = importlib.import_module("apps.masterplan.bootstrap")
    circuit_breaker = importlib.import_module("AINDY.kernel.circuit_breaker")
    fake_cb = SimpleNamespace(state=circuit_breaker.CircuitState.OPEN, opened_at="now")

    monkeypatch.setattr("AINDY.kernel.circuit_breaker.get_openai_circuit_breaker", lambda: fake_cb)

    with pytest.raises(RuntimeError, match="OpenAI circuit breaker is open"):
        module.masterplan_health_check()


def test_social_health_check_happy_path(monkeypatch, fake_sessionlocal):
    module = importlib.import_module("apps.social.bootstrap")
    session, factory = fake_sessionlocal

    monkeypatch.setattr("AINDY.db.database.SessionLocal", factory)
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "client-id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "client-secret")

    assert module.social_health_check() is True
    assert session.closed is True


def test_tasks_health_check_happy_path(monkeypatch, fake_sessionlocal):
    module = importlib.import_module("apps.tasks.bootstrap")
    session, factory = fake_sessionlocal

    monkeypatch.setattr("AINDY.db.database.SessionLocal", factory)

    assert module.tasks_health_check() is True
    assert session.closed is True


def test_identity_health_check_happy_path(monkeypatch, fake_sessionlocal):
    module = importlib.import_module("apps.identity.bootstrap")
    session, factory = fake_sessionlocal

    monkeypatch.setattr("AINDY.db.database.SessionLocal", factory)

    assert module.identity_health_check() is True
    assert session.closed is True


@pytest.mark.parametrize(
    ("module_name", "domain_name"),
    [
        ("apps.freelance.bootstrap", "freelance"),
        ("apps.masterplan.bootstrap", "masterplan"),
        ("apps.social.bootstrap", "social"),
        ("apps.tasks.bootstrap", "tasks"),
        ("apps.identity.bootstrap", "identity"),
    ],
)
def test_register_registers_domain_health_check(monkeypatch, module_name, domain_name):
    module = importlib.import_module(module_name)
    calls: list[tuple[str, object]] = []

    for helper_name in (
        "_register_models",
        "_register_router",
        "_register_routers",
        "_register_route_prefixes",
        "_register_response_adapters",
        "_register_events",
        "_register_jobs",
        "_register_scheduled_jobs",
        "_register_async_jobs",
        "_register_agent_tools",
        "_register_agent_capabilities",
        "_register_agent_ranking",
        "_register_capture_rules",
        "_register_flows",
        "_register_flow_results",
        "_register_flow_plans",
        "_register_required_flow_nodes",
        "_register_required_syscalls",
        "_register_syscalls",
    ):
        if hasattr(module, helper_name):
            monkeypatch.setattr(module, helper_name, lambda: None)

    domain_registry = importlib.import_module("AINDY.platform_layer.domain_health").domain_health_registry
    monkeypatch.setattr(domain_registry, "register", lambda domain, fn: calls.append((domain, fn)))
    monkeypatch.setattr("AINDY.platform_layer.registry.register_health_check", lambda *_args, **_kwargs: None)

    module.register()

    assert calls
    assert calls[0][0] == domain_name
    assert callable(calls[0][1])

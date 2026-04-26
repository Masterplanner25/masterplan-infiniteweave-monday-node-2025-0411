from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_get_context_for_prompt_returns_string(monkeypatch):
    module = importlib.import_module("apps.identity.public")

    class FakeIdentityService:
        def __init__(self, db, user_id):
            self.db = db
            self.user_id = user_id

        def get_context_for_prompt(self) -> str:
            return "context"

    monkeypatch.setattr(
        "apps.identity.services.identity_service.IdentityService",
        FakeIdentityService,
    )

    assert module.get_context_for_prompt("user-1", db=object()) == "context"


def test_get_context_for_prompt_returns_empty_string_on_failure(monkeypatch):
    module = importlib.import_module("apps.identity.public")

    class BrokenIdentityService:
        def __init__(self, db, user_id):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "apps.identity.services.identity_service.IdentityService",
        BrokenIdentityService,
    )

    assert module.get_context_for_prompt("bad-user", db=object()) == ""


def test_get_recent_memory_returns_list(monkeypatch):
    module = importlib.import_module("apps.identity.public")

    monkeypatch.setattr(
        "apps.identity.services.identity_boot_service.get_recent_memory",
        lambda user_id, db, *, context="infinity_loop": [{"id": 1, "context": context}],
    )

    result = module.get_recent_memory("user-1", db=object(), context="infinity_loop")

    assert isinstance(result, list)
    assert result == [{"id": 1, "context": "infinity_loop"}]


def test_get_user_metrics_returns_dict(monkeypatch):
    module = importlib.import_module("apps.identity.public")

    monkeypatch.setattr(
        "apps.identity.services.identity_boot_service.get_user_metrics",
        lambda user_id, db: {"score": 0.8},
    )

    result = module.get_user_metrics("user-1", db=object())

    assert isinstance(result, dict)
    assert result == {"score": 0.8}


def test_observe_identity_event_returns_true(monkeypatch):
    module = importlib.import_module("apps.identity.public")
    observed = {}

    class FakeIdentityService:
        def __init__(self, db, user_id):
            self.db = db
            self.user_id = user_id

        def observe(self, *, event_type, context):
            observed["event_type"] = event_type
            observed["context"] = context

    monkeypatch.setattr(
        "apps.identity.services.identity_service.IdentityService",
        FakeIdentityService,
    )

    result = module.observe_identity_event(
        "user-1",
        db=object(),
        event_type="masterplan_locked",
        context={"posture": "stable"},
    )

    assert result is True
    assert observed == {"event_type": "masterplan_locked", "context": {"posture": "stable"}}


def test_identity_public_contract():
    module = importlib.import_module("apps.identity.public")

    assert module.PUBLIC_API_VERSION == "1.0"
    assert "get_context_for_prompt" in module.__all__
    assert "get_recent_memory" in module.__all__
    assert "get_user_metrics" in module.__all__

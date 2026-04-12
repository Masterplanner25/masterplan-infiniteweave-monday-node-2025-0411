from __future__ import annotations

from types import SimpleNamespace

import pytest


class _FakeDB:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_perform_external_call_success_emits_start_and_complete(monkeypatch):
    from AINDY.platform_layer.external_call_service import perform_external_call

    events = []
    monkeypatch.setattr(
        "platform_layer.external_call_service.emit_system_event",
        lambda **kwargs: events.append(kwargs["event_type"]),
    )
    monkeypatch.setattr(
        "platform_layer.external_call_service.emit_error_event",
        lambda **kwargs: events.append(f"error.{kwargs['error_type']}"),
    )

    result = perform_external_call(
        service_name="openai",
        db=_FakeDB(),
        user_id=None,
        endpoint="chat.completions.create",
        model="gpt-4o",
        method="openai.chat",
        operation=lambda: {"ok": True},
    )

    assert result == {"ok": True}
    assert events == ["external.call.started", "external.call.completed"]


def test_perform_external_call_failure_emits_failed_and_error(monkeypatch):
    from AINDY.platform_layer.external_call_service import perform_external_call

    events = []
    monkeypatch.setattr(
        "platform_layer.external_call_service.emit_system_event",
        lambda **kwargs: events.append(kwargs["event_type"]),
    )
    monkeypatch.setattr(
        "platform_layer.external_call_service.emit_error_event",
        lambda **kwargs: events.append(f"error.{kwargs['error_type']}"),
    )

    with pytest.raises(RuntimeError, match="boom"):
        perform_external_call(
            service_name="http",
            db=_FakeDB(),
            endpoint="https://example.test",
            method="GET",
            operation=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    assert events == [
        "external.call.started",
        "external.call.failed",
        "error.external_call",
    ]


def test_perform_external_call_raises_when_required_event_emission_fails(monkeypatch):
    from AINDY.platform_layer.external_call_service import perform_external_call
    from AINDY.core.system_event_service import SystemEventEmissionError

    def _emit_system_event(**kwargs):
        raise SystemEventEmissionError("missing event")

    monkeypatch.setattr("platform_layer.external_call_service.emit_system_event", _emit_system_event)
    monkeypatch.setattr("platform_layer.external_call_service.emit_error_event", lambda **kwargs: None)

    with pytest.raises(SystemEventEmissionError, match="missing event"):
        perform_external_call(
            service_name="openai",
            db=_FakeDB(),
            endpoint="chat.completions.create",
            model="gpt-4o",
            method="openai.chat",
            operation=lambda: {"ok": True},
        )


def test_generate_embedding_routes_through_external_call_wrapper(monkeypatch):
    from AINDY.memory import embedding_service
    captured = {}

    monkeypatch.setattr(embedding_service, "get_client", lambda: SimpleNamespace())

    def _perform_external_call(**kwargs):
        captured.update(
            service_name=kwargs["service_name"],
            endpoint=kwargs["endpoint"],
            model=kwargs["model"],
            method=kwargs["method"],
        )
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1] * embedding_service.EMBEDDING_DIMENSIONS)]
        )

    monkeypatch.setattr(embedding_service, "perform_external_call", _perform_external_call)

    result = embedding_service.generate_embedding("hello")

    assert len(result) == embedding_service.EMBEDDING_DIMENSIONS
    assert captured == {
        "service_name": "openai",
        "endpoint": "embeddings.create",
        "model": embedding_service.EMBEDDING_MODEL,
        "method": "openai.embeddings",
    }



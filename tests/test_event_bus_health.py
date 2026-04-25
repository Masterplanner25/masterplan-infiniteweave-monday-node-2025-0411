from __future__ import annotations

def test_event_bus_get_status_returns_dict():
    from AINDY.kernel.event_bus import get_event_bus

    bus = get_event_bus()
    status = bus.get_status()
    assert isinstance(status, dict)
    assert "enabled" in status
    assert "mode" in status
    assert status["mode"] in {"cross-instance", "local-only", "disabled", "unknown"}


def test_event_bus_mode_is_local_when_redis_unavailable(monkeypatch):
    from AINDY.kernel.event_bus import EventBus

    bus = EventBus.__new__(EventBus)
    bus._enabled = True
    bus._subscriber_thread = None
    monkeypatch.setattr(bus, "_is_redis_connected", lambda: False)
    monkeypatch.setattr(bus, "_is_subscriber_running", lambda: False)

    assert bus._get_propagation_mode() == "local-only"


def test_health_endpoint_includes_wait_resume(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "wait_resume" in data
    assert "propagation_mode" in data["wait_resume"]
    assert "safe_for_multi_instance" in data["wait_resume"]

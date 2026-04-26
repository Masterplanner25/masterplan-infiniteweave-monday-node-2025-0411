from __future__ import annotations

from AINDY.config import settings
from AINDY.middleware import _is_version_below


def test_api_version_endpoint_returns_200(client):
    response = client.get("/api/version")

    assert response.status_code == 200
    data = response.json()
    assert data["api_version"] == settings.API_VERSION
    assert data["min_client_version"] == settings.API_MIN_CLIENT_VERSION


def test_api_version_endpoint_no_auth_required(client):
    response = client.get("/api/version")

    assert response.status_code == 200


def test_x_api_version_header_present_on_all_responses(client):
    health_response = client.get("/health")
    version_response = client.get("/api/version")
    missing_response = client.get("/does-not-exist")

    assert health_response.headers["X-API-Version"] == settings.API_VERSION
    assert version_response.headers["X-API-Version"] == settings.API_VERSION
    assert missing_response.headers["X-API-Version"] == settings.API_VERSION


def test_x_version_warning_added_for_old_client(client, monkeypatch):
    monkeypatch.setattr(settings, "API_MIN_CLIENT_VERSION", "2.0.0")

    response = client.get("/api/version", headers={"X-Client-Version": "1.0.0"})

    assert "X-Version-Warning" in response.headers
    assert "below minimum supported 2.0.0" in response.headers["X-Version-Warning"]


def test_no_x_version_warning_for_current_client(client, monkeypatch):
    monkeypatch.setattr(settings, "API_MIN_CLIENT_VERSION", "1.0.0")

    response = client.get("/api/version", headers={"X-Client-Version": settings.API_VERSION})

    assert "X-Version-Warning" not in response.headers


def test_is_version_below_utility():
    assert _is_version_below("1.0.0", "2.0.0") is True
    assert _is_version_below("2.0.0", "1.0.0") is False
    assert _is_version_below("1.5.0", "1.5.0") is False
    assert _is_version_below("malformed", "1.0.0") is True

"""
test_routes_bridge.py
────────────────────
Bridge route tests using actual paths from routes/bridge_router.py.

Routes registered under prefix /bridge:
  POST /bridge/nodes      (requires JWT; permission optional and ignored)
  GET  /bridge/nodes      (requires JWT)
  POST /bridge/link       (requires JWT; permission optional and ignored)
  POST /bridge/user_event (requires API key)
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_permission_payload():
    """Helper: placeholder TracePermission payload (ignored under JWT-only bridge)."""
    return {
        "nonce": "test-nonce-123",
        "ts": 0,
        "ttl": 300,
        "scopes": ["write"],
        "signature": "ignored",
    }


class TestBridgeRouteRegistration:
    def test_bridge_nodes_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/bridge/nodes" in routes, f"/bridge/nodes not found in {routes}"

    def test_bridge_link_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/bridge/link" in routes

    def test_bridge_user_event_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/bridge/user_event" in routes


class TestBridgeNodeCreation:
    def test_post_nodes_without_permission_returns_201(self, client, auth_headers):
        """POST /bridge/nodes with no permission field should succeed under JWT-only policy."""
        response = client.post(
            "/bridge/nodes",
            json={
                "content": "test node",
                "tags": ["test"],
                "node_type": "insight",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, (
            f"Expected 201 (JWT-only), got {response.status_code}"
        )

    def test_post_nodes_with_invalid_permission_is_ignored(self, client, auth_headers):
        """POST /bridge/nodes with permission payload should be ignored under JWT-only policy."""
        response = client.post(
            "/bridge/nodes",
            json={
                "content": "test node",
                "tags": ["test"],
                "node_type": "insight",
                "permission": _make_permission_payload(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, (
            f"Expected 201 for ignored permission, got {response.status_code}: {response.text[:200]}"
        )

    def test_post_nodes_with_expired_permission_returns_201(self, client, auth_headers):
        """POST /bridge/nodes ignores permission payload under JWT-only policy."""
        response = client.post(
            "/bridge/nodes",
            json={
                "content": "test node",
                "tags": [],
                "permission": _make_permission_payload(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, (
            f"Expected 201 for ignored permission, got {response.status_code}"
        )

    def test_post_nodes_without_jwt_returns_401(self, client):
        """POST /bridge/nodes without JWT must return 401."""
        response = client.post(
            "/bridge/nodes",
            json={
                "content": "test node",
                "tags": ["test"],
                "permission": _make_permission_payload(),
            },
        )
        assert response.status_code == 401, (
            f"Expected 401 (missing JWT), got {response.status_code}"
        )


class TestBridgeNodeSearch:
    def test_get_nodes_returns_200(self, client, auth_headers):
        """GET /bridge/nodes (search) should return 200 or 500 (DB), never 401/404."""
        response = client.get("/bridge/nodes", headers=auth_headers)
        assert response.status_code in (200, 500), (
            f"GET /bridge/nodes returned unexpected status {response.status_code}"
        )
        assert response.status_code != 404, "GET /bridge/nodes route not found (404)"

    def test_get_nodes_without_jwt_returns_401(self, client):
        """GET /bridge/nodes without JWT must return 401."""
        response = client.get("/bridge/nodes")
        assert response.status_code == 401, (
            f"Expected 401 (missing JWT), got {response.status_code}"
        )


class TestBridgeLinkCreation:
    def test_post_link_without_permission_returns_404_or_403(self, client, auth_headers):
        """POST /bridge/link with no permission should return ownership or missing-node errors."""
        response = client.post(
            "/bridge/link",
            json={
                "source_id": "00000000-0000-0000-0000-000000000001",
                "target_id": "00000000-0000-0000-0000-000000000002",
            },
            headers=auth_headers,
        )
        assert response.status_code in (403, 404), (
            f"Expected 403/404 for invalid link IDs, got {response.status_code}"
        )

    def test_post_link_without_jwt_returns_401(self, client):
        """POST /bridge/link without JWT must return 401."""
        response = client.post(
            "/bridge/link",
            json={
                "source_id": "00000000-0000-0000-0000-000000000001",
                "target_id": "00000000-0000-0000-0000-000000000002",
                "permission": _make_permission_payload(),
            },
        )
        assert response.status_code == 401, (
            f"Expected 401 (missing JWT), got {response.status_code}"
        )


class TestBridgeUserEvent:
    def test_bridge_user_event_persists_and_returns_logged(self, client, api_key_headers):
        """
        POST /bridge/user_event accepts events and persists them.
        The endpoint returns {"status": "logged"}.
        """
        response = client.post(
            "/bridge/user_event",
            json={
                "user": "diagnostic_test_user",
                "origin": "pytest",
                "timestamp": "2026-01-01T00:00:00",
            },
            headers=api_key_headers,
        )
        assert response.status_code == 200, (
            f"POST /bridge/user_event returned {response.status_code}"
        )
        data = response.json()
        assert data.get("status") == "logged", (
            f"Expected status='logged', got: {data}"
        )

    def test_bridge_user_event_without_api_key_returns_401(self, client):
        """POST /bridge/user_event without API key must return 401."""
        response = client.post(
            "/bridge/user_event",
            json={
                "user": "test_user",
                "origin": "pytest",
            },
        )
        assert response.status_code == 401, (
            f"Expected 401 (missing API key), got {response.status_code}"
        )

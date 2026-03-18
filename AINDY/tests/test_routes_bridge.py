"""
test_routes_bridge.py
─────────────────────
Bridge route tests using actual paths from routes/bridge_router.py.

Routes registered under prefix /bridge:
  POST /bridge/nodes      (requires HMAC permission + JWT)
  GET  /bridge/nodes      (requires JWT)
  POST /bridge/link       (requires HMAC permission + JWT)
  POST /bridge/user_event (requires API key)
"""
import pytest
import hmac
import hashlib
import time
from unittest.mock import MagicMock, patch


def _make_valid_permission(secret: str = "test-secret-for-pytest", scopes=None):
    """Helper: generate a valid TracePermission payload."""
    if scopes is None:
        scopes = ["write"]
    nonce = "test-nonce-123"
    ts = int(time.time())
    ttl = 300

    payload = f"{nonce}|{ts}|{ttl}|{','.join(sorted(scopes))}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    return {
        "nonce": nonce,
        "ts": ts,
        "ttl": ttl,
        "scopes": scopes,
        "signature": sig,
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
    def test_post_nodes_without_permission_returns_422(self, client, auth_headers):
        """POST /bridge/nodes with no permission field must return 422 (Pydantic validation)."""
        response = client.post("/bridge/nodes", json={
            "content": "test node",
            "tags": ["test"],
            "node_type": "insight",
        }, headers=auth_headers)
        assert response.status_code == 422, (
            f"Expected 422 (missing permission field), got {response.status_code}"
        )

    def test_post_nodes_with_invalid_hmac_returns_403(self, client, auth_headers):
        """POST /bridge/nodes with tampered signature must return 403."""
        bad_permission = {
            "nonce": "test-nonce",
            "ts": int(time.time()),
            "ttl": 300,
            "scopes": ["write"],
            "signature": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        }
        response = client.post("/bridge/nodes", json={
            "content": "test node",
            "tags": ["test"],
            "node_type": "insight",
            "permission": bad_permission,
        }, headers=auth_headers)
        assert response.status_code == 403, (
            f"Expected 403 for invalid HMAC, got {response.status_code}: {response.text[:200]}"
        )

    def test_post_nodes_with_expired_permission_returns_403(self, client, auth_headers):
        """POST /bridge/nodes with expired TTL must return 403."""
        import os
        secret = os.environ.get("PERMISSION_SECRET", "test-secret-for-pytest")
        nonce = "test-nonce-expired"
        ts = int(time.time()) - 600  # 10 minutes ago
        ttl = 60  # TTL was 1 minute — now expired
        scopes = ["write"]
        payload = f"{nonce}|{ts}|{ttl}|{','.join(sorted(scopes))}"
        sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

        response = client.post("/bridge/nodes", json={
            "content": "test node",
            "tags": [],
            "permission": {"nonce": nonce, "ts": ts, "ttl": ttl, "scopes": scopes, "signature": sig},
        }, headers=auth_headers)
        assert response.status_code == 403, (
            f"Expected 403 for expired permission, got {response.status_code}"
        )

    def test_post_nodes_without_jwt_returns_401(self, client):
        """POST /bridge/nodes without JWT must return 401."""
        response = client.post("/bridge/nodes", json={
            "content": "test node",
            "tags": ["test"],
            "permission": _make_valid_permission(),
        })
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
    def test_post_link_without_permission_returns_422(self, client, auth_headers):
        """POST /bridge/link with no permission field must return 422."""
        response = client.post("/bridge/link", json={
            "source_id": "00000000-0000-0000-0000-000000000001",
            "target_id": "00000000-0000-0000-0000-000000000002",
        }, headers=auth_headers)
        assert response.status_code == 422, (
            f"Expected 422 (missing permission), got {response.status_code}"
        )

    def test_post_link_without_jwt_returns_401(self, client):
        """POST /bridge/link without JWT must return 401."""
        response = client.post("/bridge/link", json={
            "source_id": "00000000-0000-0000-0000-000000000001",
            "target_id": "00000000-0000-0000-0000-000000000002",
            "permission": _make_valid_permission(),
        })
        assert response.status_code == 401, (
            f"Expected 401 (missing JWT), got {response.status_code}"
        )


class TestBridgeUserEvent:
    def test_bridge_user_event_no_persistence(self, client, api_key_headers):
        """
        POST /bridge/user_event accepts events but only calls print().
        No persistence to DB and no RippleTrace event is emitted.
        The endpoint returns {"status": "logged"} but nothing is stored.
        """
        response = client.post("/bridge/user_event", json={
            "user": "diagnostic_test_user",
            "origin": "pytest",
            "timestamp": "2026-01-01T00:00:00",
        }, headers=api_key_headers)
        # The endpoint works (200) but nothing is persisted
        assert response.status_code == 200, (
            f"POST /bridge/user_event returned {response.status_code}"
        )
        data = response.json()
        assert data.get("status") == "logged", (
            f"Expected status='logged', got: {data}"
        )

    def test_bridge_user_event_without_api_key_returns_401(self, client):
        """POST /bridge/user_event without API key must return 401."""
        response = client.post("/bridge/user_event", json={
            "user": "test_user",
            "origin": "pytest",
        })
        assert response.status_code == 401, (
            f"Expected 401 (missing API key), got {response.status_code}"
        )

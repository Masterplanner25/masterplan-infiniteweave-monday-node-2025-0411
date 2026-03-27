"""
test_routes_health.py
─────────────────────
Health endpoint tests.

NOTE: The health check at GET /health/ makes LIVE HTTP requests to
127.0.0.1:8000 (self-ping) and also queries the DB. In unit test context
the DB is not available, so the endpoint will return a response with
"degraded" status but should still return HTTP 200.
"""
import pytest
import time
from unittest.mock import MagicMock, patch


class TestHealthEndpoint:
    def test_health_route_registered(self, app):
        """GET /health/ must be registered in the router."""
        routes = [r.path for r in app.routes]
        assert "/health/" in routes, (
            f"GET /health/ not found in routes: {routes}"
        )

    def test_health_returns_200(self, client):
        """
        GET /health/ must return HTTP 200 even when DB or components are degraded.
        The endpoint catches exceptions internally and reports degraded status.
        """
        # The DB dependency will fail (no real postgres), but the route catches it
        response = client.get("/health/")
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text[:200]}"
        )

    def test_health_response_has_status_field(self, client):
        """Response JSON must contain a 'status' field."""
        response = client.get("/health/")
        if response.status_code == 200:
            data = response.json()
            assert "status" in data, f"Missing 'status' field in: {data}"

    def test_health_response_has_components_field(self, client):
        """Response JSON must contain a 'components' field."""
        response = client.get("/health/")
        if response.status_code == 200:
            data = response.json()
            assert "components" in data, f"Missing 'components' field in: {data}"

    def test_health_response_has_timestamp(self, client):
        """Response JSON must contain a 'timestamp' field."""
        response = client.get("/health/")
        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data, f"Missing 'timestamp' field in: {data}"

    def test_health_check_is_reasonably_fast(self, client):
        """
        DIAGNOSTIC: Health check should return in under 30 seconds.

        The health router makes HTTP requests to 127.0.0.1:8000 with a 5s timeout
        each (3 endpoints × 5s = up to 15s max). This documents the self-ping design
        as a performance concern.
        """
        start = time.time()
        response = client.get("/health/")
        elapsed = time.time() - start
        assert elapsed < 30.0, (
            f"Health check took {elapsed:.1f}s — exceeds 30s limit. "
            "Root cause: health router makes 3 live HTTP self-pings with 5s timeout each."
        )

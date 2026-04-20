import time


class TestHealthEndpoint:
    def test_health_route_registered(self, app):
        """GET /health/ and /health/detail must be registered in the router."""
        routes = [r.path for r in app.routes]
        assert "/health/" in routes, (
            f"GET /health/ not found in routes: {routes}"
        )
        assert "/health/detail" in routes, (
            f"GET /health/detail not found in routes: {routes}"
        )

    def test_health_returns_200(self, client):
        response = client.get("/health/")
        assert response.status_code == 200

    def test_health_response_has_status_field(self, client):
        response = client.get("/health/")
        data = response.json()
        assert "status" in data, f"Missing 'status' field in: {data}"

    def test_health_response_has_dependencies_field(self, client):
        response = client.get("/health/")
        data = response.json()
        assert "dependencies" in data, f"Missing 'dependencies' field in: {data}"

    def test_health_response_has_timestamp(self, client):
        response = client.get("/health/")
        data = response.json()
        assert "timestamp" in data, f"Missing 'timestamp' field in: {data}"

    def test_health_check_is_reasonably_fast(self, client):
        start = time.time()
        response = client.get("/health/")
        elapsed = time.time() - start
        assert elapsed < 30.0, (
            f"Health check took {elapsed:.1f}s - exceeds 30s limit."
        )
        assert response.status_code == 200

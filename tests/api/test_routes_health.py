import time


class TestHealthEndpoint:
    def test_health_route_registered(self, app):
        """GET health routes must be registered in the router."""
        routes = [r.path for r in app.routes]
        assert "/health/" in routes, (
            f"GET /health/ not found in routes: {routes}"
        )
        assert "/health/detail" in routes, (
            f"GET /health/detail not found in routes: {routes}"
        )
        assert "/health/deep" in routes, (
            f"GET /health/deep not found in routes: {routes}"
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

    def test_deep_health_returns_200(self, client):
        response = client.get("/health/deep")
        assert response.status_code == 200

    def test_deep_health_has_required_keys(self, client):
        response = client.get("/health/deep")
        data = response.json()
        assert "status" in data
        assert "instance_id" in data
        assert "checks" in data
        assert all(
            key in data["checks"]
            for key in ("database", "redis", "mongo", "scheduler", "flow_registry", "worker", "nodus", "ai_providers", "quota_backend")
        )
        assert "circuit" in data["checks"]["ai_providers"]["openai"]
        assert "circuit" in data["checks"]["ai_providers"]["deepseek"]

    def test_deep_health_reports_nodus_not_configured_when_env_unset(self, client, monkeypatch):
        monkeypatch.delenv("NODUS_SOURCE_PATH", raising=False)
        response = client.get("/health/deep")
        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["nodus"]["status"] == "not_configured"
        assert data["checks"]["nodus"]["detail"] == "NODUS_SOURCE_PATH not set"

    def test_deep_health_reports_openai_circuit_as_degraded(self, client):
        from AINDY.kernel.circuit_breaker import get_openai_circuit_breaker

        breaker = get_openai_circuit_breaker()

        def _fail():
            raise RuntimeError("down")

        breaker.reset()
        for _ in range(breaker.failure_threshold):
            try:
                breaker.call(_fail)
            except RuntimeError:
                pass

        response = client.get("/health/deep")
        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["ai_providers"]["status"] == "degraded"
        assert data["checks"]["ai_providers"]["openai"]["circuit"] == "open"

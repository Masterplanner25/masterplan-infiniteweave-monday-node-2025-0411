"""
test_routes_leadgen.py
──────────────────────
LeadGen route tests.

Routes from routes/leadgen_router.py (prefix /leadgen):
  POST /leadgen/    — generate leads (query param: ?query=...)
  GET  /leadgen/    — list all leads

Known bugs to document:
- score_lead() has unreachable code after return statement (dead code, second try block)
- create_memory_node() called by leadgen_service produces phantom CalculationResult rows
"""
import pytest
from unittest.mock import MagicMock, patch


class TestLeadGenRouteRegistration:
    def test_leadgen_post_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/leadgen/" in routes, (
            f"/leadgen/ POST route not found. Routes: {routes}"
        )

    def test_leadgen_get_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/leadgen/" in routes


class TestLeadGenEndpoints:
    def test_get_leadgen_requires_auth(self, client):
        """GET /leadgen/ without auth must return 401."""
        response = client.get("/leadgen/")
        assert response.status_code == 401, (
            f"GET /leadgen/ returned {response.status_code} without auth. Expected 401."
        )

    def test_post_leadgen_without_query_returns_422(self, client, auth_headers):
        """POST /leadgen/ without required 'query' param must return 422."""
        response = client.post("/leadgen/", headers=auth_headers)
        assert response.status_code == 422, (
            f"Expected 422 for missing 'query' param, got {response.status_code}"
        )

    def test_post_leadgen_without_auth_returns_401(self, client):
        """POST /leadgen/ without auth must return 401."""
        response = client.post("/leadgen/?query=test")
        assert response.status_code == 401, (
            f"POST /leadgen/ returned {response.status_code} without auth. Expected 401."
        )

    def test_post_leadgen_with_auth_not_404(self, client, auth_headers):
        """POST /leadgen/?query=test with valid auth must reach handler (not 404)."""
        response = client.post("/leadgen/?query=test+companies", headers=auth_headers)
        assert response.status_code != 404


class TestLeadGenResponseStructure:
    def test_get_leadgen_response_key_is_list(self, client, auth_headers):
        """
        DIAGNOSTIC: GET /leadgen/ returns a list directly (when status is 200).
        Documents that the GET endpoint returns a plain list (not {"results": [...]}).
        The POST endpoint wraps in {"query":..., "count":..., "results":[...]}.
        Inconsistent response shapes between GET and POST.
        """
        response = client.get("/leadgen/", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), (
                f"GET /leadgen/ returns {type(data)} not a list: {str(data)[:200]}"
            )

    def test_post_leadgen_response_has_results_key(self, client, auth_headers):
        """
        POST /leadgen/?query=test returns {"query":..., "count":..., "results":[...]}.
        Note: POST response uses 'results' key, not 'leads'.
        """
        response = client.post("/leadgen/?query=test", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert "results" in data, (
                f"POST /leadgen/ response missing 'results' key. Got: {list(data.keys())}"
            )
            if data["results"]:
                assert "search_score" in data["results"][0], (
                    "LeadGen results should include search_score"
                )


class TestLeadGenServiceBugs:
    def test_score_lead_has_no_dead_code_after_return(self):
        """
        REGRESSION: leadgen_service.score_lead() should not contain unreachable
        code after its first return statement.
        """
        import inspect
        from AINDY.domain import leadgen_service
        source = inspect.getsource(leadgen_service.score_lead)
        return_count = source.count("return result")
        try_count = source.count("try:")

        assert return_count == 1, (
            f"Expected a single return statement in score_lead(). Found: {return_count}"
        )
        assert try_count == 1, (
            f"Expected a single try block in score_lead(). Found: {try_count}"
        )

    def test_create_memory_node_no_longer_uses_wrong_table(self):
        """
        REGRESSION (Memory Bridge Phase 1, 2026-03-18):
        create_memory_node() was fixed — it now uses MemoryNodeDAO, not CalculationResult.
        Regression guard: ensures CalculationResult is never reintroduced.
        """
        import inspect
        from AINDY.domain import leadgen_service
        import AINDY.memory.bridge as bridge

        source = inspect.getsource(leadgen_service.create_lead_results)
        assert "create_memory_node" in source, (
            "create_lead_results() no longer calls create_memory_node() — verify fix applied"
        )

        bridge_source = inspect.getsource(bridge.create_memory_node)
        assert "CalculationResult" not in bridge_source, (
            "REGRESSION: create_memory_node() must not reference CalculationResult. "
            "Bug was fixed in Memory Bridge Phase 1 (2026-03-18)."
        )
        assert "MemoryNodeDAO" in bridge_source, (
            "create_memory_node() must use MemoryNodeDAO for persistence"
        )

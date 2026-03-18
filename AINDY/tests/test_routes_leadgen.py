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
    def test_get_leadgen_without_db_returns_non_404(self, client):
        """GET /leadgen/ must reach the handler (not return 404)."""
        response = client.get("/leadgen/")
        assert response.status_code != 404, (
            f"GET /leadgen/ returned 404 — route not registered"
        )

    def test_post_leadgen_without_query_returns_422(self, client):
        """POST /leadgen/ without required 'query' param must return 422."""
        response = client.post("/leadgen/")
        assert response.status_code == 422, (
            f"Expected 422 for missing 'query' param, got {response.status_code}"
        )

    def test_post_leadgen_with_query_param_not_404(self, client):
        """POST /leadgen/?query=test must reach the handler (not 404)."""
        response = client.post("/leadgen/?query=test+companies")
        assert response.status_code != 404


class TestLeadGenResponseStructure:
    def test_get_leadgen_response_key_is_list(self, client):
        """
        DIAGNOSTIC: GET /leadgen/ returns a list directly.
        Documents that the GET endpoint returns a plain list (not {"results": [...]}).
        The POST endpoint wraps in {"query":..., "count":..., "results":[...]}.
        Inconsistent response shapes between GET and POST.
        """
        response = client.get("/leadgen/")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), (
                f"GET /leadgen/ returns {type(data)} not a list: {str(data)[:200]}"
            )

    def test_post_leadgen_response_has_results_key(self, client):
        """
        POST /leadgen/?query=test returns {"query":..., "count":..., "results":[...]}.
        Note: POST response uses 'results' key, not 'leads'.
        """
        response = client.post("/leadgen/?query=test")
        if response.status_code == 200:
            data = response.json()
            assert "results" in data, (
                f"POST /leadgen/ response missing 'results' key. Got: {list(data.keys())}"
            )


class TestLeadGenServiceBugs:
    def test_score_lead_has_dead_code_after_return(self):
        """
        DIAGNOSTIC: leadgen_service.score_lead() has unreachable code after its first
        return statement (a second try/except block with a different model call).
        This test documents the dead code bug by inspecting source.
        """
        import inspect
        from services import leadgen_service

        source = inspect.getsource(leadgen_service.score_lead)
        # The function has two 'return result' statements and two 'try:' blocks
        # Count occurrences of key patterns
        return_count = source.count("return result")
        try_count = source.count("try:")

        assert return_count >= 2, (
            f"Expected 2+ return statements in score_lead() — unreachable code may have been fixed. "
            f"Found: {return_count}"
        )
        assert try_count >= 2, (
            f"Expected 2+ try blocks in score_lead() — dead code may have been removed. "
            f"Found: {try_count}"
        )

    def test_create_memory_node_called_with_wrong_table(self):
        """
        DIAGNOSTIC: leadgen_service.create_lead_results() calls create_memory_node()
        which writes to calculation_results (wrong table).
        This test documents the phantom row creation side-effect.
        """
        import inspect
        from services import leadgen_service
        from bridge import bridge

        source = inspect.getsource(leadgen_service.create_lead_results)
        assert "create_memory_node" in source, (
            "create_lead_results() no longer calls create_memory_node() — verify fix applied"
        )

        bridge_source = inspect.getsource(bridge.create_memory_node)
        assert "CalculationResult" in bridge_source, (
            "BUG FIXED: create_memory_node() no longer uses CalculationResult. "
            "This test can now be removed."
        )

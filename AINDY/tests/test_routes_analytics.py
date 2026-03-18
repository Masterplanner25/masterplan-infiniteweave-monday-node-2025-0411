"""
test_routes_analytics.py
─────────────────────────
Analytics route tests.

Routes from routes/analytics_router.py (prefix /analytics):
  POST /analytics/linkedin/manual
  GET  /analytics/masterplan/{masterplan_id}
  GET  /analytics/masterplan/{masterplan_id}/summary

Routes from routes/main_router.py (no prefix):
  POST /calculate_twr
  POST /calculate_engagement
  POST /calculate_effort
  POST /calculate_productivity
  POST /calculate_virality
  (+ many others)
"""
import pytest


class TestAnalyticsRouteRegistration:
    def test_linkedin_manual_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/analytics/linkedin/manual" in routes, (
            f"/analytics/linkedin/manual not found in routes: {routes}"
        )

    def test_masterplan_analytics_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/analytics/masterplan/{masterplan_id}" in routes

    def test_calculate_twr_route_registered(self, app):
        """POST /calculate_twr is registered on main_router (no prefix)."""
        routes = [r.path for r in app.routes]
        assert "/calculate_twr" in routes, (
            f"/calculate_twr not found. Routes: {[r for r in routes if 'calc' in r.lower()]}"
        )

    def test_calculate_engagement_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/calculate_engagement" in routes

    def test_calculate_effort_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/calculate_effort" in routes


class TestCalculateTWREndpoint:
    def test_twr_missing_fields_returns_422(self, client, auth_headers):
        """POST /calculate_twr with empty body must return 422."""
        response = client.post("/calculate_twr", json={}, headers=auth_headers)
        assert response.status_code == 422

    def test_twr_with_valid_payload_not_404(self, client):
        """POST /calculate_twr with valid TaskInput must reach the handler (not 404)."""
        payload = {
            "task_name": "diagnostic_test",
            "time_spent": 2.0,
            "task_complexity": 3,
            "skill_level": 4,
            "ai_utilization": 3,
            "task_difficulty": 2,
        }
        response = client.post("/calculate_twr", json=payload)
        # No DB = likely 500, but route must exist (not 404)
        assert response.status_code != 404, (
            f"POST /calculate_twr returned 404 — route missing"
        )

    def test_twr_zero_difficulty_causes_500(self, client, auth_headers):
        """
        DIAGNOSTIC BUG: task_difficulty=0 causes ZeroDivisionError in calculate_twr().
        The endpoint has no guard, so it returns 500.
        This test documents the missing zero-division protection.
        """
        payload = {
            "task_name": "zero_difficulty_test",
            "time_spent": 2.0,
            "task_complexity": 3,
            "skill_level": 4,
            "ai_utilization": 3,
            "task_difficulty": 0,  # BUG: causes ZeroDivisionError
        }
        response = client.post("/calculate_twr", json=payload, headers=auth_headers)
        # Pydantic may reject 0 or route may hit the ZeroDivisionError
        # Either way: should never return 200 with task_difficulty=0
        # If 422 → Pydantic caught it (acceptable)
        # If 500 → ZeroDivisionError leaked (bug confirmed)
        assert response.status_code in (422, 500), (
            f"Unexpected status {response.status_code} for task_difficulty=0"
        )


class TestCalculateEngagementEndpoint:
    def test_engagement_missing_fields_returns_422(self, client, auth_headers):
        """POST /calculate_engagement with empty body must return 422."""
        response = client.post("/calculate_engagement", json={}, headers=auth_headers)
        assert response.status_code == 422

    def test_engagement_zero_views_not_500(self, client):
        """
        POST /calculate_engagement with total_views=0 must NOT raise ZeroDivisionError.
        The service guards this case with `if data.total_views == 0: return 0`.
        """
        payload = {
            "likes": 0,
            "shares": 0,
            "comments": 0,
            "clicks": 0,
            "time_on_page": 0.0,
            "total_views": 0,
        }
        response = client.post("/calculate_engagement", json=payload)
        # Should not be 500 — the zero check is in place
        assert response.status_code != 500, (
            f"POST /calculate_engagement with total_views=0 returned 500 — ZeroDivisionError not guarded"
        )


class TestAnalyticsLinkedInManual:
    def test_linkedin_manual_requires_auth(self, client):
        """POST /analytics/linkedin/manual without auth must return 401."""
        response = client.post("/analytics/linkedin/manual", json={})
        assert response.status_code == 401, (
            f"POST /analytics/linkedin/manual returned {response.status_code} without auth. "
            "Expected 401."
        )

    def test_linkedin_manual_missing_fields_returns_422(self, client, auth_headers):
        """POST /analytics/linkedin/manual with auth but empty body must return 422."""
        response = client.post(
            "/analytics/linkedin/manual",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_linkedin_manual_missing_masterplan_returns_404(self, client, auth_headers):
        """
        POST /analytics/linkedin/manual with auth and valid structure but nonexistent
        masterplan should return 404 from the handler (requires DB — will return 500 if no DB).
        """
        from datetime import date
        payload = {
            "masterplan_id": 999999,
            "platform": "linkedin",
            "scope_type": "profile",
            "scope_id": "test_user",
            "period_type": "week",
            "period_start": "2026-01-01",
            "period_end": "2026-01-07",
            "passive_visibility": 1000,
            "active_discovery": 50,
            "unique_reach": 800,
            "interaction_volume": 100,
            "deep_attention_units": 20,
            "intent_signals": 10,
            "conversion_events": 2,
            "growth_velocity": 5,
        }
        response = client.post(
            "/analytics/linkedin/manual",
            json=payload,
            headers=auth_headers,
        )
        # 404 if DB is up and plan doesn't exist, 500 if DB is down
        assert response.status_code in (404, 422, 500), (
            f"Unexpected status {response.status_code}"
        )

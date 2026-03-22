"""
test_routes_dashboard.py
--------------------------------
Dashboard overview route tests.
"""
from unittest.mock import MagicMock

from db.database import get_db


def _empty_db():
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.all.return_value = []
    db.query.return_value = query
    return db


class TestDashboardOverview:
    def test_dashboard_requires_auth(self, client):
        response = client.get("/dashboard/overview")
        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}: {response.text[:200]}"
        )

    def test_dashboard_overview_shape(self, app, client, auth_headers):
        app.dependency_overrides[get_db] = lambda: _empty_db()
        try:
            response = client.get("/dashboard/overview", headers=auth_headers)
            assert response.status_code == 200, (
                f"Expected 200 but got {response.status_code}: {response.text[:200]}"
            )
            payload = response.json()
            assert payload.get("status") == "ok", f"Unexpected status: {payload}"
            overview = payload.get("overview")
            assert isinstance(overview, dict), f"Missing overview dict: {payload}"
            for key in ["system_timestamp", "author_count", "recent_authors", "recent_ripples"]:
                assert key in overview, f"Missing key '{key}' in overview: {overview}"
        finally:
            app.dependency_overrides.pop(get_db, None)

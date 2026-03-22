"""
test_routes_observability.py
--------------------------------
Observability endpoint tests.
"""
from unittest.mock import MagicMock

from db.database import get_db


def _build_mock_db():
    db = MagicMock()
    base_query = MagicMock()
    base_query.filter.return_value = base_query
    base_query.count.side_effect = [0, 0, 0, 0]
    base_query.order_by.return_value = base_query
    base_query.limit.return_value = base_query
    base_query.all.return_value = []
    base_query.scalar.return_value = 0.0
    db.query.return_value = base_query
    return db


class TestObservabilityRoutes:
    def test_observability_requires_auth(self, client):
        response = client.get("/observability/requests")
        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}: {response.text[:200]}"
        )

    def test_observability_returns_summary_shape(self, app, client, auth_headers):
        mock_db = _build_mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            response = client.get("/observability/requests", headers=auth_headers)
            assert response.status_code == 200, (
                f"Expected 200 but got {response.status_code}: {response.text[:200]}"
            )
            payload = response.json()
            assert "summary" in payload, f"Missing summary in response: {payload}"
            assert "recent" in payload, f"Missing recent in response: {payload}"
            assert "recent_errors" in payload, f"Missing recent_errors in response: {payload}"
            summary = payload["summary"]
            for key in [
                "total_requests",
                "window_hours",
                "window_requests",
                "total_errors",
                "window_errors",
                "avg_latency_ms",
            ]:
                assert key in summary, f"Missing summary key '{key}' in {summary}"
        finally:
            app.dependency_overrides.pop(get_db, None)

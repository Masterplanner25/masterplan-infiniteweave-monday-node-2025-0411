"""
test_routes_memory_metrics.py
--------------------------------
Memory metrics routes tests.
"""
from unittest.mock import MagicMock

import runtime.memory.metrics_store as metrics_store


class StubMetricsStore:
    def get_summary(self, *, user_id, db):
        return {
            "avg_impact_score": 0.1,
            "positive_impact_rate": 0.5,
            "zero_impact_rate": 0.4,
            "negative_impact_rate": 0.1,
            "total_runs": 2,
        }

    def get_recent(self, *, user_id, db, limit=20):
        return []


class TestMemoryMetricsRoutes:
    def test_memory_metrics_requires_auth(self, client):
        response = client.get("/memory/metrics")
        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}: {response.text[:200]}"
        )

    def test_memory_metrics_summary_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(metrics_store, "MemoryMetricsStore", StubMetricsStore)
        response = client.get("/memory/metrics", headers=auth_headers)
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text[:200]}"
        )
        payload = response.json()
        for key in [
            "avg_impact_score",
            "positive_impact_rate",
            "zero_impact_rate",
            "negative_impact_rate",
            "total_runs",
        ]:
            assert key in payload, f"Missing key '{key}' in response: {payload}"

    def test_memory_metrics_dashboard_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(metrics_store, "MemoryMetricsStore", StubMetricsStore)
        response = client.get("/memory/metrics/dashboard", headers=auth_headers)
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text[:200]}"
        )
        payload = response.json()
        for key in ["summary", "recent_runs", "insights"]:
            assert key in payload, f"Missing key '{key}' in response: {payload}"

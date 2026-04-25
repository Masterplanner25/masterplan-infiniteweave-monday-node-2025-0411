from __future__ import annotations

from unittest.mock import patch


def _paths(app) -> list[str]:
    return [route.path for route in app.routes]


class TestCausalInsightRoutes:
    def test_causal_graph_route_registered(self, app):
        assert "/rippletrace/causal/graph" in _paths(app)

    def test_causal_graph_requires_auth(self, client):
        response = client.get("/rippletrace/causal/graph")
        assert response.status_code == 401

    def test_causal_graph_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.causal_engine.build_causal_graph",
            return_value={"nodes": [], "causal_edges": []},
        ):
            response = client.get("/rippletrace/causal/graph", headers=auth_headers)

        assert response.status_code == 200


class TestNarrativeInsightRoutes:
    def test_narrative_summary_route_registered(self, app):
        assert "/rippletrace/narrative/summary" in _paths(app)

    def test_narrative_summary_requires_auth(self, client):
        response = client.get("/rippletrace/narrative/summary")
        assert response.status_code == 401

    def test_narrative_summary_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.narrative_engine.narrative_summary",
            return_value=[],
        ):
            response = client.get("/rippletrace/narrative/summary", headers=auth_headers)

        assert response.status_code == 200


class TestPredictionInsightRoutes:
    def test_predictions_summary_route_registered(self, app):
        assert "/rippletrace/predictions/summary" in _paths(app)

    def test_predictions_summary_requires_auth(self, client):
        response = client.get("/rippletrace/predictions/summary")
        assert response.status_code == 401

    def test_predictions_summary_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.prediction_engine.prediction_summary",
            return_value={"total_predicted_spikes": 0, "total_declining": 0, "total_emerging_signals": 0},
        ):
            response = client.get("/rippletrace/predictions/summary", headers=auth_headers)

        assert response.status_code == 200


class TestRecommendationInsightRoutes:
    def test_recommendations_system_route_registered(self, app):
        assert "/rippletrace/recommendations/system" in _paths(app)

    def test_recommendations_system_requires_auth(self, client):
        response = client.get("/rippletrace/recommendations/system")
        assert response.status_code == 401

    def test_recommendations_system_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.recommendation_engine.system_recommendations",
            return_value=[],
        ):
            response = client.get("/rippletrace/recommendations/system", headers=auth_headers)

        assert response.status_code == 200


class TestLearningInsightRoutes:
    def test_learning_stats_route_registered(self, app):
        assert "/rippletrace/learning/stats" in _paths(app)

    def test_learning_stats_requires_auth(self, client):
        response = client.get("/rippletrace/learning/stats")
        assert response.status_code == 401

    def test_learning_stats_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.learning_engine.learning_stats",
            return_value={"total_predictions": 0, "evaluated": 0, "accuracy": 0.0, "false_positive_rate": 0.0, "false_negative_rate": 0.0},
        ):
            response = client.get("/rippletrace/learning/stats", headers=auth_headers)

        assert response.status_code == 200


class TestPlaybookInsightRoutes:
    def test_playbooks_route_registered(self, app):
        assert "/rippletrace/playbooks" in _paths(app)

    def test_playbooks_requires_auth(self, client):
        response = client.get("/rippletrace/playbooks")
        assert response.status_code == 401

    def test_playbooks_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.playbook_engine.list_playbooks",
            return_value=[],
        ):
            response = client.get("/rippletrace/playbooks", headers=auth_headers)

        assert response.status_code == 200


class TestStrategyInsightRoutes:
    def test_strategies_build_route_registered_before_param_route(self, app):
        paths = _paths(app)
        assert "/rippletrace/strategies/build" in paths
        assert "/rippletrace/strategies/{strategy_id}" in paths
        assert paths.index("/rippletrace/strategies/build") < paths.index("/rippletrace/strategies/{strategy_id}")

    def test_strategies_requires_auth(self, client):
        response = client.get("/rippletrace/strategies")
        assert response.status_code == 401

    def test_strategies_build_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.strategy_engine.build_strategies",
            return_value=[],
        ):
            response = client.get("/rippletrace/strategies/build", headers=auth_headers)

        assert response.status_code == 200


class TestEventCausalityRoutes:
    def test_event_downstream_route_registered(self, app):
        assert "/rippletrace/event/{event_id}/downstream" in _paths(app)

    def test_event_downstream_requires_auth(self, client):
        response = client.get("/rippletrace/event/test/downstream")
        assert response.status_code == 401

    def test_event_downstream_returns_200_with_auth(self, client, auth_headers):
        with patch(
            "apps.rippletrace.services.rippletrace_service.get_downstream_effects",
            return_value=[],
        ):
            response = client.get("/rippletrace/event/test/downstream", headers=auth_headers)

        assert response.status_code == 200

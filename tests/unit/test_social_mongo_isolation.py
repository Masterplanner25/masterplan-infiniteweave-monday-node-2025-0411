from __future__ import annotations

from unittest.mock import MagicMock

from pymongo.errors import PyMongoError


def test_summarize_social_performance_returns_degraded_when_mongo_errors(monkeypatch):
    from apps.social.services import social_performance_service

    mock_posts = MagicMock()
    mock_posts.find.side_effect = PyMongoError("mongo exploded")
    mock_db = {"posts": mock_posts}
    mock_client = {"aindy_social_layer": mock_db}

    class _Client:
        def __getitem__(self, name):
            return mock_db

    monkeypatch.setattr(
        social_performance_service,
        "get_mongo_client",
        lambda: _Client(),
    )

    result = social_performance_service.summarize_social_performance(user_id="user-1")

    assert result == {
        "status": "degraded",
        "data": [],
        "reason": "mongo exploded",
    }


def test_social_analytics_route_returns_200_when_service_is_degraded(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "apps.social.routes.social_router.summarize_social_performance",
        lambda **kwargs: {
            "status": "degraded",
            "data": [],
            "reason": "mongodb_unavailable",
        },
    )

    response = client.get("/social/analytics", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SUCCESS"
    assert payload["data"]["status"] == "degraded"
    assert payload["data"]["data"] == []
    assert payload["data"]["reason"] == "mongodb_unavailable"


def test_health_payload_includes_platform_mongodb(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert "platform" in payload
    assert "mongodb" in payload["platform"]

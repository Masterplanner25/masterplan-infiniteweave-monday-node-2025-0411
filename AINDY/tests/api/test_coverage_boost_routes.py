from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_analytics_manual_route_smoke(client, app, auth_headers, monkeypatch):
    from db.database import get_db

    fake_plan = SimpleNamespace(id=1)
    fake_db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = fake_plan
    fake_db.query.return_value = query

    app.dependency_overrides[get_db] = lambda: fake_db
    monkeypatch.setattr(
        "runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {"status": "SUCCESS", "data": {"ingested": True}},
    )

    response = client.post(
        "/analytics/linkedin/manual",
        json={
            "masterplan_id": 1,
            "period_type": "weekly",
            "period_start": "2026-01-01",
            "period_end": "2026-01-07",
            "scope_type": "aggregate",
            "impressions": 100,
            "members_reached": 90,
        },
        headers=auth_headers,
    )

    app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    assert response.json()["ingested"] is True


def test_freelance_orders_route_smoke(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {"status": "SUCCESS", "data": {"orders": []}},
    )

    response = client.get("/freelance/orders", headers=auth_headers)

    assert response.status_code == 200
    assert "orders" in response.text


def test_social_get_profile_route_smoke(client, app, auth_headers):
    from db.mongo_setup import get_mongo_db

    profiles = MagicMock()
    profiles.find_one.return_value = {"username": "alice", "bio": "hello"}
    fake_mongo = {"profiles": profiles}

    app.dependency_overrides[get_mongo_db] = lambda: fake_mongo

    response = client.get("/social/profile/alice", headers=auth_headers)

    app.dependency_overrides.pop(get_mongo_db, None)
    assert response.status_code == 200
    assert "alice" in response.text

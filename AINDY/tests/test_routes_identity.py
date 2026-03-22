"""
test_routes_identity.py
--------------------------------
Identity routes tests.
"""
from unittest.mock import MagicMock

import services.identity_service as identity_service


class StubIdentityService:
    def __init__(self, db, user_id):
        self.db = db
        self.user_id = user_id

    def get_profile(self):
        return {"user_id": self.user_id, "profile": {}}

    def update_explicit(self, **kwargs):
        return {"changes_recorded": len(kwargs), "changes": [], "profile": {}}

    def get_evolution_summary(self):
        return {"observation_count": 0, "total_changes": 0, "dimensions_evolved": []}

    def get_context_for_prompt(self):
        return ""


class TestIdentityRoutes:
    def test_identity_requires_auth(self, client):
        response = client.get("/identity/")
        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}: {response.text[:200]}"
        )

    def test_identity_profile_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(identity_service, "IdentityService", StubIdentityService)
        response = client.get("/identity/", headers=auth_headers)
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text[:200]}"
        )
        payload = response.json()
        assert "user_id" in payload, f"Missing user_id in response: {payload}"
        assert "profile" in payload, f"Missing profile in response: {payload}"

    def test_identity_context_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(identity_service, "IdentityService", StubIdentityService)
        response = client.get("/identity/context", headers=auth_headers)
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text[:200]}"
        )
        payload = response.json()
        for key in ["context", "is_empty", "message"]:
            assert key in payload, f"Missing key '{key}' in response: {payload}"

    def test_identity_evolution_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(identity_service, "IdentityService", StubIdentityService)
        response = client.get("/identity/evolution", headers=auth_headers)
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text[:200]}"
        )
        payload = response.json()
        for key in ["observation_count", "total_changes", "dimensions_evolved"]:
            assert key in payload, f"Missing key '{key}' in response: {payload}"

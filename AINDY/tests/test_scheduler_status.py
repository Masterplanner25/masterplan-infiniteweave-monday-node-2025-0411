"""
Sprint N+9 Phase 3 — GET /observability/scheduler/status endpoint tests.

Groups:
  1. is_background_leader() helper (2 tests)
  2. GET /observability/scheduler/status response shape (5 tests)
"""
import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — is_background_leader helper
# ─────────────────────────────────────────────────────────────────────────────

class TestIsBackgroundLeader:
    def test_returns_false_when_no_owner(self):
        import services.task_services as ts
        original = ts._BACKGROUND_OWNER_ID
        try:
            ts._BACKGROUND_OWNER_ID = None
            assert ts.is_background_leader() is False
        finally:
            ts._BACKGROUND_OWNER_ID = original

    def test_returns_true_when_owner_matches_instance(self):
        import services.task_services as ts
        original = ts._BACKGROUND_OWNER_ID
        try:
            instance_id = ts._get_instance_id()
            ts._BACKGROUND_OWNER_ID = instance_id
            assert ts.is_background_leader() is True
        finally:
            ts._BACKGROUND_OWNER_ID = original


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — GET /observability/scheduler/status
# ─────────────────────────────────────────────────────────────────────────────

def _make_db_mock(lease_row=None):
    """Return a DB mock whose .query().filter().first() returns lease_row."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = lease_row
    return db


def _make_client(lease_row=None):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI, Depends
    from routes.observability_router import router
    from services.auth_service import get_current_user
    from db.database import get_db

    app = FastAPI()

    def override_auth():
        return {"sub": "test-user-id"}

    def override_db():
        return _make_db_mock(lease_row=lease_row)

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    app.include_router(router)
    return TestClient(app)


class TestSchedulerStatusEndpoint:
    def test_returns_200(self):
        client = _make_client()
        with patch("services.scheduler_service.get_scheduler", side_effect=RuntimeError("not started")), \
             patch("services.task_services.is_background_leader", return_value=False):
            resp = client.get("/observability/scheduler/status")
        assert resp.status_code == 200

    def test_response_has_required_keys(self):
        client = _make_client()
        with patch("services.scheduler_service.get_scheduler", side_effect=RuntimeError("not started")), \
             patch("services.task_services.is_background_leader", return_value=False):
            resp = client.get("/observability/scheduler/status")
        data = resp.json()
        assert "scheduler_running" in data
        assert "is_leader" in data
        assert "lease" in data

    def test_scheduler_running_false_when_not_started(self):
        client = _make_client()
        with patch("services.scheduler_service.get_scheduler", side_effect=RuntimeError("not started")), \
             patch("services.task_services.is_background_leader", return_value=False):
            resp = client.get("/observability/scheduler/status")
        assert resp.json()["scheduler_running"] is False

    def test_scheduler_running_true_when_started(self):
        client = _make_client()
        mock_sched = MagicMock()
        mock_sched.running = True
        with patch("services.scheduler_service.get_scheduler", return_value=mock_sched), \
             patch("services.task_services.is_background_leader", return_value=True):
            resp = client.get("/observability/scheduler/status")
        assert resp.json()["scheduler_running"] is True
        assert resp.json()["is_leader"] is True

    def test_lease_null_when_no_row(self):
        # Pass lease_row=None so db.query().filter().first() returns None
        client = _make_client(lease_row=None)
        with patch("services.scheduler_service.get_scheduler", side_effect=RuntimeError("not started")), \
             patch("services.task_services.is_background_leader", return_value=False):
            resp = client.get("/observability/scheduler/status")
        assert resp.json()["lease"] is None

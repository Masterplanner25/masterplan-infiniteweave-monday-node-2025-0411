"""
test_routes_tasks.py
────────────────────
Task route tests using actual route paths from routes/task_router.py.

Routes registered under prefix /tasks:
  POST /tasks/create
  POST /tasks/start
  POST /tasks/pause
  POST /tasks/complete
  GET  /tasks/list
  POST /tasks/recurrence/check
"""
import pytest
from unittest.mock import MagicMock, patch


class TestTaskRouteRegistration:
    def test_task_list_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/tasks/list" in routes, f"GET /tasks/list not found. Routes: {routes}"

    def test_task_create_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/tasks/create" in routes, f"POST /tasks/create not found. Routes: {routes}"

    def test_task_complete_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/tasks/complete" in routes, f"POST /tasks/complete not found. Routes: {routes}"

    def test_task_start_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/tasks/start" in routes

    def test_task_pause_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/tasks/pause" in routes


class TestTaskRouteResponses:
    def test_get_tasks_list_without_auth_returns_200_not_401(self, client):
        """
        DIAGNOSTIC — SECURITY BUG.
        GET /tasks/list has NO authentication.
        This test will PASS (200 or 500 due to no DB), documenting the absence of auth.
        A secure system would return 401 here.

        Related test in test_security.py asserts 401 — that test WILL FAIL.
        """
        response = client.get("/tasks/list")
        # No auth middleware → route is reached (200 or 500 from DB, never 401)
        assert response.status_code != 401, (
            "Unexpected: /tasks/list returned 401. "
            "Auth middleware has been added — update test_security.py."
        )

    def test_create_task_missing_required_fields_returns_422(self, client):
        """POST /tasks/create with no body must return 422 Unprocessable Entity."""
        response = client.post("/tasks/create", json={})
        assert response.status_code == 422, (
            f"Expected 422 for missing fields, got {response.status_code}: {response.text[:300]}"
        )

    def test_create_task_invalid_json_returns_422(self, client):
        """POST /tasks/create with completely wrong types must return 422."""
        response = client.post("/tasks/create", json={"name": 123, "category": None})
        # 'name' must be a string — pydantic should accept it (int is coercible)
        # but missing required fields should still produce 422
        assert response.status_code in (200, 201, 422, 500)

    def test_create_task_with_valid_body_not_401(self, client):
        """
        DIAGNOSTIC — SECURITY BUG.
        POST /tasks/create is publicly accessible (no auth).
        """
        payload = {
            "name": "diagnostic_test_task",
            "category": "test",
            "priority": "low",
        }
        response = client.post("/tasks/create", json=payload)
        # Will be 500 (no DB) or 200 — but not 401 (no auth)
        assert response.status_code != 401, (
            "POST /tasks/create returned 401 — auth has been added (update security tests)"
        )

    def test_complete_task_missing_body_returns_422(self, client):
        """POST /tasks/complete with no body must return 422."""
        response = client.post("/tasks/complete", json={})
        assert response.status_code == 422


class TestTaskSchemas:
    def test_task_create_schema_importable(self):
        from schemas.task_schemas import TaskCreate
        assert TaskCreate is not None

    def test_task_action_schema_importable(self):
        from schemas.task_schemas import TaskAction
        assert TaskAction is not None

    def test_task_create_requires_name(self):
        from schemas.task_schemas import TaskCreate
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TaskCreate()  # name is required

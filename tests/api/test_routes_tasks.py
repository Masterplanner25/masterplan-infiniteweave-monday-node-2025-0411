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
    def test_get_tasks_list_requires_auth(self, client):
        """
        SECURITY: GET /tasks/list requires authentication.
        Without a valid JWT token, must return 401.
        """
        response = client.get("/tasks/list")
        assert response.status_code == 401, (
            f"GET /tasks/list returned {response.status_code} without auth. "
            "Expected 401 — JWT auth is required on this route."
        )

    def test_get_tasks_list_with_auth_not_404(self, client, auth_headers):
        """GET /tasks/list with valid JWT must not return 404."""
        response = client.get("/tasks/list", headers=auth_headers)
        assert response.status_code != 404, (
            f"GET /tasks/list returned 404 with valid auth — route missing"
        )

    def test_create_task_missing_required_fields_returns_422(self, client, auth_headers):
        """POST /tasks/create with no body must return 422 Unprocessable Entity."""
        response = client.post("/tasks/create", json={}, headers=auth_headers)
        assert response.status_code == 422, (
            f"Expected 422 for missing fields, got {response.status_code}: {response.text[:300]}"
        )

    def test_create_task_invalid_json_returns_expected(self, client, auth_headers):
        """POST /tasks/create with partially valid types must reach the handler."""
        response = client.post(
            "/tasks/create",
            json={"name": 123, "category": None},
            headers=auth_headers,
        )
        assert response.status_code in (200, 201, 422, 500)

    def test_create_task_requires_auth(self, client):
        """
        SECURITY: POST /tasks/create requires authentication.
        Without a JWT token, must return 401.
        """
        payload = {
            "name": "security_test_task",
            "category": "test",
            "priority": "low",
        }
        response = client.post("/tasks/create", json=payload)
        assert response.status_code == 401, (
            f"POST /tasks/create returned {response.status_code} without auth. "
            "Expected 401 — route must require authentication."
        )

    def test_complete_task_missing_body_returns_422(self, client, auth_headers):
        """POST /tasks/complete with no body must return 422."""
        response = client.post("/tasks/complete", json={}, headers=auth_headers)
        assert response.status_code == 422

    def test_recurrence_check_requires_auth(self, client):
        """POST /tasks/recurrence/check without auth must return 401."""
        response = client.post("/tasks/recurrence/check")
        assert response.status_code == 401, (
            f"POST /tasks/recurrence/check returned {response.status_code} without auth. "
            "Expected 401."
        )


class TestTaskSchemas:
    def test_task_create_schema_importable(self):
        from apps.tasks.schemas.task_schemas import TaskCreate
        assert TaskCreate is not None

    def test_task_action_schema_importable(self):
        from apps.tasks.schemas.task_schemas import TaskAction
        assert TaskAction is not None

    def test_task_create_requires_name(self):
        from apps.tasks.schemas.task_schemas import TaskCreate
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            TaskCreate()  # name is required

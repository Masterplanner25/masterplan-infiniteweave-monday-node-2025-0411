from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

platform_router = importlib.import_module("routes.platform_router")


@pytest.fixture
def platform_client():
    app = FastAPI()
    app.include_router(platform_router.router)
    app.dependency_overrides[platform_router.get_current_user] = lambda: {"sub": "user-1"}
    app.dependency_overrides[platform_router.get_db] = lambda: "db-session"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_dispatch_syscall_uses_default_capabilities_for_jwt(platform_client):
    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = {
        "status": "success",
        "data": {"nodes": []},
        "trace_id": "trace-1",
        "execution_unit_id": "exec-1",
        "syscall": "sys.v1.memory.read",
        "version": "v1",
        "duration_ms": 5,
        "error": None,
        "warning": None,
    }

    with patch("kernel.syscall_registry.DEFAULT_NODUS_CAPABILITIES", ["memory.read", "event.emit"]), \
         patch("kernel.syscall_dispatcher.make_syscall_ctx_from_tool", return_value="ctx") as make_ctx, \
         patch("kernel.syscall_dispatcher.get_dispatcher", return_value=dispatcher):
        response = platform_client.post(
            "/platform/syscall",
            json={"name": "sys.v1.memory.read", "payload": {"query": "auth"}},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    make_ctx.assert_called_once_with(user_id="user-1", capabilities=["memory.read", "event.emit"])
    dispatcher.dispatch.assert_called_once_with("sys.v1.memory.read", {"query": "auth"}, "ctx")


def test_dispatch_syscall_intersects_api_key_scopes():
    app = FastAPI()
    app.include_router(platform_router.router)
    app.dependency_overrides[platform_router.get_current_user] = lambda: {
        "sub": "user-1",
        "auth_type": "api_key",
        "api_key_scopes": ["memory.read", "unknown.scope"],
    }
    app.dependency_overrides[platform_router.get_db] = lambda: "db-session"
    client = TestClient(app)
    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = {
        "status": "success",
        "data": {},
        "trace_id": "trace-2",
        "execution_unit_id": "exec-2",
        "syscall": "sys.v1.memory.read",
        "version": "v1",
        "duration_ms": 3,
        "error": None,
        "warning": None,
    }

    try:
        with patch("kernel.syscall_registry.DEFAULT_NODUS_CAPABILITIES", ["memory.read", "event.emit"]), \
             patch("kernel.syscall_dispatcher.make_syscall_ctx_from_tool", return_value="ctx") as make_ctx, \
             patch("kernel.syscall_dispatcher.get_dispatcher", return_value=dispatcher):
            response = client.post(
                "/platform/syscall",
                json={"name": "sys.v1.memory.read", "payload": {}},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    make_ctx.assert_called_once_with(user_id="user-1", capabilities=["memory.read"])


@pytest.mark.parametrize(
    ("message", "status_code"),
    [
        ("Permission denied: missing capability memory.read", 403),
        ("Input validation failed: missing query", 422),
        ("quota exceeded for tenant", 429),
        ("Unknown syscall sys.v9.fake", 404),
    ],
)
def test_dispatch_syscall_maps_dispatcher_errors(platform_client, message, status_code):
    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = {
        "status": "error",
        "error": message,
        "trace_id": "trace-err",
        "execution_unit_id": "exec-err",
        "syscall": "sys.v1.memory.read",
        "version": "v1",
        "duration_ms": 1,
        "warning": None,
        "data": None,
    }

    with patch("kernel.syscall_registry.DEFAULT_NODUS_CAPABILITIES", ["memory.read"]), \
         patch("kernel.syscall_dispatcher.make_syscall_ctx_from_tool", return_value="ctx"), \
         patch("kernel.syscall_dispatcher.get_dispatcher", return_value=dispatcher):
        response = platform_client.post(
            "/platform/syscall",
            json={"name": "sys.v1.memory.read", "payload": {}},
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["error"] == message


def test_list_memory_path_normalizes_and_filters_tags(platform_client):
    dao = MagicMock()
    dao.query_path.return_value = [{"id": "m1", "path": "/memory/user-1/tasks/test"}]

    with patch("memory.memory_address_space.normalize_path", return_value="/memory/user-1/tasks/*") as normalize, \
         patch("memory.memory_address_space.validate_tenant_path") as validate, \
         patch("db.dao.memory_node_dao.MemoryNodeDAO", return_value=dao):
        response = platform_client.get(
            "/platform/memory",
            params={
                "path": "/memory/user-1/tasks/*",
                "query": "task",
                "tags": "alpha,beta",
                "limit": 2,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "nodes": [{"id": "m1", "path": "/memory/user-1/tasks/test"}],
        "count": 1,
        "path": "/memory/user-1/tasks/*",
    }
    normalize.assert_called_once_with("/memory/user-1/tasks/*")
    validate.assert_called_once_with("/memory/user-1/tasks/*", "user-1")
    dao.query_path.assert_called_once_with(
        path_expr="/memory/user-1/tasks/*",
        query="task",
        tags=["alpha", "beta"],
        user_id="user-1",
        limit=2,
    )


def test_list_memory_path_returns_400_for_invalid_path(platform_client):
    with patch("memory.memory_address_space.normalize_path", return_value="/memory/user-2/tasks/*"), \
         patch("memory.memory_address_space.validate_tenant_path", side_effect=PermissionError("tenant mismatch")):
        response = platform_client.get(
            "/platform/memory",
            params={"path": "/memory/user-2/tasks/*"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "tenant mismatch"


def test_memory_trace_returns_404_when_no_chain(platform_client):
    dao = MagicMock()
    dao.causal_trace.return_value = []

    with patch("memory.memory_address_space.normalize_path", return_value="/memory/user-1/tasks/root"), \
         patch("memory.memory_address_space.validate_tenant_path"), \
         patch("db.dao.memory_node_dao.MemoryNodeDAO", return_value=dao):
        response = platform_client.get(
            "/platform/memory/trace",
            params={"path": "/memory/user-1/tasks/root", "depth": 7},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "No node found at path"
    dao.causal_trace.assert_called_once_with(
        path="/memory/user-1/tasks/root",
        depth=7,
        user_id="user-1",
    )

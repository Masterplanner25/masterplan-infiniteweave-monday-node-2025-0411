from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from db.dao.memory_trace_dao import MemoryTraceDAO


class DummyTraceDAO:
    def __init__(self, db):
        self.db = db

    def create_trace(self, **kwargs):
        return {"id": "trace-1", **kwargs}

    def list_traces(self, **kwargs):
        return [{"id": "trace-1", "user_id": kwargs.get("user_id")}]

    def get_trace(self, trace_id, **kwargs):
        if trace_id == "trace-1":
            return {"id": "trace-1", "user_id": kwargs.get("user_id")}
        return None

    def get_trace_nodes(self, trace_id, **kwargs):
        if trace_id == "trace-1":
            return [{"id": "tn-1", "node_id": "node-1", "position": 0}]
        return []

    def append_node(self, **kwargs):
        if kwargs.get("trace_id") != "trace-1":
            return None
        return {"id": "tn-1", "trace_id": "trace-1", "node_id": kwargs.get("node_id"), "position": 0}


class DummyMemoryDAO:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, node_id, user_id=None):
        if node_id == "node-1":
            return {"id": "node-1", "user_id": user_id}
        return None


class TestMemoryTraceDAO:
    def test_create_trace_returns_id(self):
        db = MagicMock()
        dao = MemoryTraceDAO(db)
        result = dao.create_trace(user_id="user-1", title="Trace")
        assert result["user_id"] == "user-1"
        assert result.get("id")

    def test_append_node_missing_trace(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        dao = MemoryTraceDAO(db)
        result = dao.append_node(trace_id="missing", node_id="node-1", user_id="user-1")
        assert result is None


class TestMemoryTraceRoutes:
    def test_trace_routes(self, client, auth_headers, monkeypatch):
        import importlib

        router = importlib.import_module("routes.memory_trace_router")

        monkeypatch.setattr(router, "MemoryTraceDAO", DummyTraceDAO)
        monkeypatch.setattr(router, "MemoryNodeDAO", DummyMemoryDAO)

        response = client.post(
            "/memory/traces",
            headers=auth_headers,
            json={"title": "Trace"},
        )
        assert response.status_code == 201
        assert response.json()["id"] == "trace-1"

        response = client.get("/memory/traces", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["count"] == 1

        response = client.get("/memory/traces/trace-1", headers=auth_headers)
        assert response.status_code == 200

        response = client.get("/memory/traces/trace-1/nodes", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["count"] == 1

        response = client.post(
            "/memory/traces/trace-1/append",
            headers=auth_headers,
            json={"node_id": "node-1"},
        )
        assert response.status_code == 201

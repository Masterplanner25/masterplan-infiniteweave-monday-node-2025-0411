from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.db.models.automation_log import AutomationLog
from AINDY.memory.embedding_jobs import EMBEDDING_JOB_NAME
from AINDY.memory.embedding_jobs import process_embedding_job
from AINDY.memory.memory_persistence import MemoryNodeModel


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr("main.init_mongo", lambda: None)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_memory_create_returns_pending_embedding_and_enqueues_job(
    client,
    db_session,
    test_user,
    auth_headers,
):
    captured_calls = []

    def _mock_enqueue(memory_id, *, user_id=None, trace_id=None, db=None):
        captured_calls.append({"memory_id": memory_id, "user_id": user_id})
        return memory_id

    with patch("AINDY.memory.embedding_jobs.enqueue_embedding", side_effect=_mock_enqueue):
        response = client.post(
            "/memory/nodes",
            headers=auth_headers,
            json={
                "content": "Async embedding memory",
                "source": "pytest",
                "tags": ["async", "embedding"],
                "node_type": "insight",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    data = payload.get("data", payload)
    assert data["embedding_status"] == "pending"

    db_session.expire_all()
    node = (
        db_session.query(MemoryNodeModel)
        .filter(MemoryNodeModel.id == uuid.UUID(data["id"]))
        .first()
    )
    assert node is not None
    assert node.embedding is None
    assert node.embedding_status == "pending"

    # Verify enqueue_embedding was called for the created memory node
    assert len(captured_calls) >= 1
    assert any(call["memory_id"] == data["id"] for call in captured_calls)


def test_memory_recall_falls_back_to_text_when_embedding_missing(
    db_session,
    test_user,
    monkeypatch,
):
    dao = MemoryNodeDAO(db_session)
    created = dao.save(
        content="Fallback retrieval phrase",
        source="pytest",
        tags=["fallback"],
        user_id=str(test_user.id),
        node_type="insight",
        generate_embedding=False,
    )

    monkeypatch.setattr(
        "memory.embedding_service.generate_query_embedding",
        lambda query: [0.0] * 1536,
    )
    monkeypatch.setattr(dao, "find_similar", lambda **kwargs: [])

    recalled = dao.recall(
        query="Fallback retrieval phrase",
        limit=3,
        user_id=str(test_user.id),
    )

    assert recalled
    assert recalled[0]["id"] == created["id"]
    assert recalled[0]["embedding_status"] == "pending"


def test_embedding_job_updates_memory_status_after_background_processing(
    db_session,
    test_user,
    monkeypatch,
):
    dao = MemoryNodeDAO(db_session)
    created = dao.save(
        content="Background embedding content",
        source="pytest",
        tags=["async"],
        user_id=str(test_user.id),
        node_type="insight",
        generate_embedding=False,
    )

    monkeypatch.setattr(
        "AINDY.memory.embedding_jobs.generate_embedding",
        lambda text: [0.25] * 1536,
    )

    result = process_embedding_job(
        {"memory_id": created["id"], "trace_id": "trace-embedding-test"},
        db_session,
    )

    assert result["embedding_status"] == "complete"

    db_session.expire_all()
    node = (
        db_session.query(MemoryNodeModel)
        .filter(MemoryNodeModel.id == uuid.UUID(created["id"]))
        .first()
    )
    assert node is not None
    assert node.embedding_status == "complete"
    assert node.embedding is not None
